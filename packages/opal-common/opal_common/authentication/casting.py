import logging
import os
from typing import Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from opal_common.authentication.types import EncryptionKeyFormat, PrivateKey, PublicKey
from opal_common.logging.decorators import log_exception

logger = logging.getLogger("opal.authentication")


def to_bytes(key: str, encoding: str = "utf-8"):
    """crypto lib expect 'bytes' keys, convert 'str' keys to 'bytes'."""
    return key.encode(encoding)


def maybe_decode_multiline_key(key: str) -> bytes:
    """if key contents are passed via env var, we allow to encode multiline
    keys with a simple replace of each newline (\n) char with underscore (_).

    this method detects if the provided key contains such encoding, and
    if so reverses it.
    """
    if "\n" not in key:
        key = key.replace("_", "\n")
        if not key.endswith("\n"):
            key = key + "\n"
    return to_bytes(key)


def cast_private_key(
    value: str, key_format: EncryptionKeyFormat, passphrase: Optional[str] = None
) -> Optional[PrivateKey]:
    """Parse a string into a valid cryptographic private key.

    the string can represent a file path in which the key exists, or the
    actual key contents.
    """
    if value is None:
        return None

    if isinstance(value, PrivateKey.__args__):
        return value

    if passphrase is None:
        password = None
    else:
        password = passphrase.encode("utf-8")

    key_path = os.path.expanduser(value)
    if os.path.isfile(key_path):
        raw_key = open(key_path, "rb").read()
    else:
        raw_key = maybe_decode_multiline_key(value)

    if key_format == EncryptionKeyFormat.pem:
        return serialization.load_pem_private_key(
            raw_key, password=password, backend=default_backend()
        )

    if key_format == EncryptionKeyFormat.ssh:
        return serialization.load_ssh_private_key(
            raw_key, password=password, backend=default_backend()
        )

    if key_format == EncryptionKeyFormat.der:
        return serialization.load_der_private_key(
            raw_key, password=password, backend=default_backend()
        )


def cast_public_key(value: str, key_format: EncryptionKeyFormat) -> Optional[PublicKey]:
    """Parse a string into a valid cryptographic public key.

    the string can represent a file path in which the key exists, or the
    actual key contents.
    """
    if value is None:
        return None

    if isinstance(value, PublicKey.__args__):
        return value

    key_path = os.path.expanduser(value)
    if os.path.isfile(key_path):
        raw_key = open(key_path, "rb").read()
    elif key_format == EncryptionKeyFormat.ssh:  # ssh key format is one line
        raw_key = to_bytes(value)
    else:
        raw_key = maybe_decode_multiline_key(value)

    if key_format == EncryptionKeyFormat.pem:
        return serialization.load_pem_public_key(raw_key, backend=default_backend())

    if key_format == EncryptionKeyFormat.ssh:
        return serialization.load_ssh_public_key(raw_key, backend=default_backend())

    if key_format == EncryptionKeyFormat.der:
        return serialization.load_der_public_key(raw_key, backend=default_backend())
