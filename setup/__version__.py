"""
OPAL - Open Policy Administration Layer

OPAL is an administration layer for Open Policy Agent (OPA). It automatically discovers
changes to your authorization policies and pushes live updates to your policy agents.

Project homepage: https://github.com/authorizon/opal
"""

VERSION = (0, 1, 15)
VERSION_STRING = '.'.join(map(str,VERSION))

__version__ = VERSION_STRING
__author__ = 'Or Weis, Asaf Cohen'
__author_email__ = 'or@authorizon.com'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2021 Or Weis and Asaf Cohen'
