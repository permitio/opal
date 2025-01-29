"""Converts a semver version into a version for PyPI package
https://peps.python.org/pep-0440/

A semver prerelease will be converted into prerelease of PyPI.
A semver build will be converted into a development part of PyPI

Usage:
    python semver2pypi.py 0.1.0-rc1
    0.1.0rc1
    python semver2pypi.py 0.1.0-dev1
    0.1.0.dev1
    python semver2pypi.py 0.1.0
    0.1.0
"""

import sys

from packaging.version import Version as PyPIVersion
from semver import Version as SemVerVersion

semver_version = SemVerVersion.parse(sys.argv[1])
finalized_version = semver_version.finalize_version()
prerelease = semver_version.prerelease or ""
build = semver_version.build or ""
pypi_version = PyPIVersion(f"{finalized_version}{prerelease}{build}")
print(pypi_version)
