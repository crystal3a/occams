"""
Testing fixtures

To run the tests you'll then need to run the following command:

    py.test --db=postgres://user:pass@host/db

Also, you can reuse a database:

    py.test --db=postgres://user:pass@host/db --reuse

This is particularly handing while developing as it saves about a minute
each time the tests are run.

"""

import pytest

from sqlalchemy.schema import CreateTable
from sqlalchemy.ext.compiler import compiles


REDIS_URL = 'redis://localhost/9'

USERID = 'test_user'


def pytest_addoption(parser):
    """
    Registers a command line argument for a database URL connection string

    :param parser: The pytest command-line parser
    """
    parser.addoption('--db', action='store', help='db string for testing')
    parser.addoption('--reuse', action='store_true',
                     help='Reuses existing database')


@compiles(CreateTable, 'postgresql')
def compile_unlogged(create, compiler, **kwargs):
    """
    Updates the CREATE TABLE construct for PostgreSQL to UNLOGGED

    The benefit of this is faster writes for testing, at the cost of
    slightly slower table creation.

    See: http://www.postgresql.org/docs/9.1/static/sql-createtable.html

    :param create:      the sqlalchemy CREATE construct
    :param compiler:    the current dialect compiler

    :return: the compiled SQL string

    """
    if 'UNLOGGED' not in create.element._prefixes:
        create.element._prefixes.append('UNLOGGED')
        return compiler.visit_create_table(create)


@pytest.fixture(scope='session', autouse=True)
def create_tables(request):
    """
    Creates the database tables for the entire testing session

    :param request: The pytest context

    :returns: configured database session
    """
    from sqlalchemy import create_engine
    from occams.models.meta import Base

    db_url = request.config.getoption('--db')
    reuse = request.config.getoption('--reuse')

    engine = create_engine(db_url)

    if not reuse:
        with engine.connect() as connection:
            connection.info['blame'] = 'test_installer'
            # This is very similar to the init_db script: create tables
            # and pre-populate with expected data
            Base.metadata.create_all(connection)
            # Don't include state data since we'll be constantly truncating
            connection.execute('DELETE FROM state')

    def drop_tables():
        if not reuse:
            Base.metadata.drop_all(engine)

    request.addfinalizer(drop_tables)


@pytest.yield_fixture
def config(request):
    """
    (Integration Testing) Instantiates a Pyramid testing configuration

    :param request: The pytest context
    """

    from pyramid import testing
    import transaction

    db_url = request.config.getoption('--db')

    test_config = testing.setUp(settings={
        'sqlalchemy.url': db_url
    })

    # Load mimimum set of plugins
    test_config.include('occams.models')
    test_config.include('occams.routes')

    yield test_config

    testing.tearDown()
    transaction.abort()


@pytest.fixture
def dbsession(config):
    """
    (Integartion Testing) Instantiates a database session.

    :param config: The pyramid testing configuartion

    :returns: An instantiated sqalchemy database session
    """
    from occams import models
    import occams.models.events
    import zope.sqlalchemy

    dbsession = config.registry['dbsession_factory']()

    occams.models.events.register(dbsession)
    zope.sqlalchemy.register(dbsession)

    # Pre-configure with a blame user
    blame = models.User(key=USERID)
    dbsession.add(blame)
    dbsession.flush()
    dbsession.info['blame'] = blame

    # Other expected settings
    dbsession.info['settings'] = config.registry.settings

    # Hardcoded workflow
    dbsession.add_all([
        models.State(name=u'pending-entry', title=u'Pending Entry'),
        models.State(name=u'pending-review', title=u'Pending Review'),
        models.State(name=u'pending-correction', title=u'Pending Correction'),
        models.State(name=u'complete', title=u'Complete')
    ])

    return dbsession


@pytest.fixture
def req(dbsession):
    """
    (Integration Testing) Creates a dummy request

    The request is setup with configuration CSRF values and the expected
    ``dbsession`` property, the goal being to be be as close to a real
    database session as possible.

    Note that we must called it "req" as "request" is reserved by pytest.

    :param dbsession: The testing database session

    :returns: a configured request object
    """
    import uuid
    import mock
    from pyramid.testing import DummyRequest

    dummy_request = DummyRequest()

    # Configurable csrf token
    csrf_token = str(uuid.uuid4())
    get_csrf_token = mock.Mock(return_value=csrf_token)
    dummy_request.session.get_csrf_token = get_csrf_token
    dummy_request.headers['X-CSRF-Token'] = csrf_token

    # Attach database session for expected behavior
    dummy_request.dbsession = dbsession
    dbsession.info['request'] = dummy_request

    return dummy_request


@pytest.fixture
def factories(dbsession):
    """
    Configures the data factories

    :param dbsession: testing session fixture
    :returns: the configured factories module
    """

    import inspect
    from . import factories

    classes = inspect.getmembers(factories, inspect.isclass)

    for class_name, class_ in classes:
        if hasattr(class_, '_meta') and hasattr(class_._meta, 'model'):
            class_._meta.sqlalchemy_session = dbsession

    return factories


@pytest.fixture(scope='session')
def wsgi(request):
    """
    (Functional Testing) Sets up a full-stacked singleton WSGI app

    :param request: The pytest context

    :returns: a WSGI application
    """
    import tempfile
    import shutil
    import six
    from occams import main

    # The pyramid_who plugin requires a who file, so let's create a
    # barebones files for it...
    who_ini = tempfile.NamedTemporaryFile()
    who = six.moves.configparser.ConfigParser()
    who.add_section('general')
    who.set('general', 'request_classifier',
            'repoze.who.classifiers:default_request_classifier')
    who.set('general', 'challenge_decider',
            'repoze.who.classifiers:default_challenge_decider')
    who.set('general', 'remote_user_key', 'REMOTE_USER')
    who.write(who_ini)
    who_ini.flush()

    db_url = request.config.getoption('--db')

    tmp_dir = tempfile.mkdtemp()

    wsgi = main({}, **{
        'redis.url': REDIS_URL,
        'redis.sessions.secret': 'sekrit',

        'who.config_file': who_ini.name,
        'who.identifier_id': '',

        # Enable regular error messages so we can see useful traceback
        'debugtoolbar.enabled': True,
        'pyramid.debug_all': True,

        'webassets.debug': True,

        'occams.apps': ['occams', 'occams'],

        'sqlalchemy.url': db_url,
        'occams.groups': [],

        'celery.broker.url': REDIS_URL,
        'celery.backend.url': REDIS_URL,
        'celery.blame': 'celery@localhost',

        'studies.export.dir': '/tmp',
        'studies.export.plans': [
            'occams.exports.pid.PidPlan',
            'occams.exports.enrollment.EnrollmentPlan',
            'occams.exports.visit.VisitPlan',
            'occams.exports.schema.SchemaPlan.list_all',
        ],
        'studies.pid.package': 'occams',
        'studies.blob.dir': '/tmp',
    })

    who_ini.close()

    def cleanup():
        shutil.rmtree(tmp_dir)

    request.addfinalizer(cleanup)

    return wsgi


@pytest.yield_fixture
def app(request, wsgi, dbsession):
    """
    (Functional Testing) Initiates a user request against a WSGI stack

    :param request: The pytest context
    :param wsgi: An initialized WSGI stack
    :param dbsession: A database session for seting up pre-existing data

    :returns: a test app request against the WSGI instance
    """
    import transaction
    from webtest import TestApp
    from zope.sqlalchemy import mark_changed
    from occams import models as models

    # Save all changes up tho this point (dbsession does some configuration)
    with transaction.manager:
        blame = models.User(key='workflow@localhost')
        dbsession.add(blame)
        dbsession.flush()
        dbsession.info['blame'] = blame

        dbsession.add_all([
            models.State(name=u'pending-entry', title=u'Pending Entry'),
            models.State(name=u'pending-review', title=u'Pending Review'),
            models.State(
                name=u'pending-correction', title=u'Pending Correction'),
            models.State(name=u'complete', title=u'Complete')
        ])

    app = TestApp(wsgi)

    yield app

    with transaction.manager:
        # DELETE is dramatically faster than TRUNCATE
        # http://stackoverflow.com/a/11423886/148781
        # We also have to do this as a raw query becuase SA does
        # not have a way to invoke server-side cascade
        dbsession.execute('DELETE FROM "rostersite" CASCADE')
        dbsession.execute('DELETE FROM "study" CASCADE')
        dbsession.execute('DELETE FROM "patient" CASCADE')
        dbsession.execute('DELETE FROM "site" CASCADE')
        dbsession.execute('DELETE FROM "schema" CASCADE')
        dbsession.execute('DELETE FROM "export" CASCADE')
        dbsession.execute('DELETE FROM "state" CASCADE')
        dbsession.execute('DELETE FROM "user" CASCADE')
        mark_changed(dbsession)


@pytest.fixture
@pytest.mark.usefixtures('create_tables')
def celery(request):
    """
    (Function Testing) Sets up a celery application for testing

    :param request: The pytest context
    """
    import shutil
    import tempfile
    import mock
    from redis import StrictRedis
    from sqlalchemy import create_engine
    from occams.celery import Session
    from occams import models as models
    from occams import tasks

    settings = {
        'studies.export.dir': tempfile.mkdtemp(),
        'celery.blame': USERID
    }

    tasks.app.userid = settings['celery.blame']
    tasks.app.redis = StrictRedis.from_url(REDIS_URL)
    tasks.app.settings = settings

    db_url = request.config.getoption('--db')
    engine = create_engine(db_url)
    Session.configure(bind=engine, info={'settings': settings})
    Session.add(models.User(key=settings['celery.blame']))
    Session.flush()

    commitmock = mock.patch('occams.tasks.Session.commit')
    commitmock.start()

    def cleanup():
        commitmock.stop()
        shutil.rmtree(settings['studies.export.dir'])
        Session.remove()

    request.addfinalizer(cleanup)
