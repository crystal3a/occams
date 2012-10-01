import re

from zope import interface
from zope import schema

from occams.roster import MessageFactory as _
from occams.roster import base36


OUR_PATTERN = re.compile(r"""
    [2-9bcdfghjkmnpqrstvwxz]{3}         # No vowels or ambiguous characters
    -                                   # Separator
    [2-9bcdfghjkmnpqrstvwxz]{3}         # No vowels or ambiguous characters
    """,
    re.IGNORECASE | re.VERBOSE
    )


# lowest possible OUR number that satisfies bureaucratic requirements
START_ID = base36.decode(u'222222')


class ISite(interface.Interface):
    u"""
    An organization/entity that can issue OUR numbers.
    Useful for keeping track of OUR number origins
    """

    title = schema.TextLine(
        title=_(u'Site Title'),
        description=_(u'The name of the site, for our records.'),
        )


class IIdentifier(interface.Interface):
    u"""
    A registered OUR number
    """

    origin = schema.Object(
        title=_(u"Origin"),
        description=_(u'The site that generated the OUR number'),
        schema=ISite,
        )

    our_number = schema.Int(
        title=_(u'Raw OUR number'),
        readonly=True,
        )


class IOurNumberDistributor(interface.Interface):
    u"""
    An organization or entity that distributes OUR numbers
    """

    def get_source_name():
        u"""
        To distribute OUR numbers, the content must be able to specify a
        "source" name. This name should stay consistent in order
        to correctly report which site generates specific OUR numbers.
        """


class IOurNumberSupport(interface.Interface):
    u"""
    A behaviour that allows content to be able to assing OUR numbers.
    """

    def generate():
        u"""
        Generates an OUR number for the distributor
        """

