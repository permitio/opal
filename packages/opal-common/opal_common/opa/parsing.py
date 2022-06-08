import re
from typing import Optional

# This regex matches the package declaration at the top of a valid .rego file
REGO_PACKAGE_DECLARATION = re.compile(r"^package\s+([a-zA-Z0-9\.\"\[\]]+)$")


def get_rego_package(contents: str) -> Optional[str]:
    """try to parse the package name from rego file contents.

    return None if failed to parse (probably invalid .rego file)
    """
    lines = contents.splitlines()
    for line in lines:
        match = REGO_PACKAGE_DECLARATION.match(line)
        if match is not None:
            return match.group(1)
    return None
