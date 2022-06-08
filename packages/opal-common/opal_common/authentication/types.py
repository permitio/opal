from enum import Enum
from typing import Any, Dict

from cryptography.hazmat.primitives.asymmetric.types import (
    PRIVATE_KEY_TYPES,
    PUBLIC_KEY_TYPES,
)
from jwt.algorithms import get_default_algorithms

# custom types
PrivateKey = PRIVATE_KEY_TYPES
PublicKey = PUBLIC_KEY_TYPES
JWTClaims = Dict[str, Any]


class EncryptionKeyFormat(str, Enum):
    """represent the supported formats for storing encryption keys.

    - PEM (https://en.wikipedia.org/wiki/Privacy-Enhanced_Mail)
    - SSH (RFC4716) or short format (RFC4253, section-6.6, explained here: https://coolaj86.com/articles/the-ssh-public-key-format/)
    - DER (https://en.wikipedia.org/wiki/X.690#DER_encoding)
    """

    pem = "pem"
    ssh = "ssh"
    der = "der"


# dynamic enum because pyjwt does not define one
# see: https://pyjwt.readthedocs.io/en/stable/algorithms.html for possible values
JWTAlgorithm = Enum("JWTAlgorithm", [(k, k) for k in get_default_algorithms().keys()])
