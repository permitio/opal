"""
OPAL - Open Policy Administration Layer

OPAL is an administration layer for Open Policy Agent (OPA). It automatically discovers
changes to your authorization policies and pushes live updates to your policy agents.

Project homepage: https://github.com/permitio/opal
"""

VERSION = (0, 1, 21)
VERSION_STRING = '.'.join(map(str,VERSION))

__version__ = VERSION_STRING
__author__ = 'Or Weis, Asaf Cohen'
__author_email__ = 'or@permit.io'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2021 Or Weis and Asaf Cohen'

install_requires = [
    'fastapi==0.65.2',
    'fastapi_websocket_pubsub>=0.2.0',
    'fastapi_websocket_rpc>=0.1.21',
    'gunicorn',
    'pydantic[email]',
    'typer',
    'typing-extensions',
    'uvicorn[standard]',
]
