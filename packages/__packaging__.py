"""
OPAL - Open Policy Administration Layer

OPAL is an administration layer for Open Policy Agent (OPA). It automatically discovers
changes to your authorization policies and pushes live updates to your policy agents.

Project homepage: https://github.com/permitio/opal
"""
import os

VERSION = (0, 7, 4)
VERSION_STRING = ".".join(map(str, VERSION))

__version__ = VERSION_STRING
__author__ = "Or Weis, Asaf Cohen"
__author_email__ = "or@permit.io"
__license__ = "Apache 2.0"
__copyright__ = "Copyright 2021 Or Weis and Asaf Cohen"


def get_install_requires(here):
    """Gets the contents of install_requires from text file.

    Getting the minimum requirements from a text file allows us to pre-install
    them in docker, speeding up our docker builds and better utilizing the docker layer cache.

    The requirements in requires.txt are in fact the minimum set of packages
    you need to run OPAL (and are thus different from a "requirements.txt" file).
    """
    with open(os.path.join(here, "requires.txt")) as fp:
        return [
            line.strip() for line in fp.read().splitlines() if not line.startswith("#")
        ]
