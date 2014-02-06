try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import logging
import os
import pkg_resources

from redis import StrictRedis
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.i18n import TranslationStringFactory
from pyramid_who.whov2 import WhoV2AuthenticationPolicy
from repoze.who.config import make_middleware_with_config
from sqlalchemy import engine_from_config
from zope.dottedname.resolve import resolve

from occams.clinical.models import Session, RosterSession


__version__ = pkg_resources.require(__name__)[0].version

_ = TranslationStringFactory(__name__)

log = logging.getLogger(__name__)


def resolve_path(spec, validate=False):
    """
    Resolves an asset descriptor
    """
    if ':' in spec:
        package, path = spec.split(':')
        spec = pkg_resources.resource_filename(package, path)

    if validate:
        assert os.path.exists(spec), 'Path does not exist: %s' % spec


def cast_maybe(value, type_):
    if value is not None:
        return type_(value)


def sanitize_settings(settings):
    """
    Parses application-specific settings values
    """

    assert 'app.export_user' in settings, 'Must specify an export user'

    settings['app.export_dir'] = \
        resolve_path(settings['app.export_dir'], validate=True)

    settings['app.export_limit'] = \
        cast_maybe(settings.get('app.export_limit'), int)
    settings['app.export_expire'] = \
        cast_maybe(settings.get('app.export_expire'), int)


def main(global_config, **settings):
    """
    This function returns a Pyramid WSGI application.
    """
    sanitize_settings(settings)

    log.debug('Connecting to database...')
    Session.configure(bind=engine_from_config(settings, 'clinicaldb.'))
    RosterSession.configure(bind=engine_from_config(settings, 'rosterdb.'))

    log.debug('Initializing configuration...')
    config = Configurator(
        settings=settings,
        root_factory='.resources.RootFactory',
        authentication_policy=WhoV2AuthenticationPolicy(
            settings['who.config_file'],
            settings['who.identifier_id'],
            resolve(settings.get('who.callback',
                                 'occams.clinical.auth.groupfinder'))),
        authorization_policy=ACLAuthorizationPolicy())

    log.debug('Loadings apps listing...')
    apps = make_app_listing(settings.get('apps.config_file'))
    config.add_request_method(
        lambda r: apps,
        name='apps',
        reify=True)

    log.debug('Connecting redis...')
    redis = StrictRedis.from_url(settings['redis.url'])
    config.add_request_method(
        lambda r: redis,
        name='redis',
        reify=True)

    log.debug('Loading components...')
    config.include('.assets')
    config.include('.auth')
    config.include('.routes')
    config.include('occams.form.widgets')
    config.scan('.layouts')
    config.scan('.panels')
    config.scan('.views')
    config.commit()

    log.debug('Loading middleware...')
    app = config.make_wsgi_app()
    app = make_middleware_with_config(
        app,
        global_config,
        settings['who.config_file'])

    return app


def make_app_listing(file_name):
    """
    Generates a listing of additional services as specified in the config file.

    Parameters:
    file_name -- The config file specifing external services

    Returns:
    A listing of dictionaries.
    """
    listing = []

    if not file_name:
        return listing

    config = configparser.SafeConfigParser()
    config.read(file_name)

    if not config.has_section('main'):
        return listing

    for suite_name in config.get('main', 'suites').split():
        suite_section = 'suite:' + suite_name
        suite = {
            'name': suite_name,
            'title': config.get(suite_section, 'title'),
            'apps': [],
            }
        for app_name in config.get(suite_section, 'apps').split():
            app_section = 'app:' + app_name
            app = {
                'name': app_name,
                'title': config.get(app_section, 'title'),
                'url': config.get(app_section, 'url')}
            suite['apps'].append(app)
        listing.append(suite)

    return listing
