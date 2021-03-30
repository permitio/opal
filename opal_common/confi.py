"""
Easy Python configuration interface built on rop of python-decouple.
Adding typing support and parsing with Pydantic and Enum
"""

from typing import TypeVar, Optional, Any
from functools import partial
from pydantic import BaseModel
from decouple import config, Csv, text_type, undefined, UndefinedValueError
import string

from opal_common.authentication.types import EncryptionKeyFormat, PrivateKey, PublicKey
from opal_common.authentication.casting import cast_private_key, cast_public_key

def cast_boolean(value):
    """
    Parse an entry as a boolean.
     - all variations of "true" and 1 are treated as True
     - all variations of "false" and 0 are treated as False
    """
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        value = value.lower()
        if (value == "true" or value == "1"):
            return True
        elif value == "false" or value == "0":
            return False
        else:
            raise UndefinedValueError(f"{value} - is not a valid boolean")
    else:
        raise UndefinedValueError(f"{value} - is not a valid boolean")

def cast_pydantic(model:BaseModel):
    def cast_pydantic_by_model(value):
        if isinstance(value, str):
            return model.parse_raw(value)
        else:
            return model.parse_obj(value)
    return cast_pydantic_by_model


EnumT = TypeVar("EnumT")
T = TypeVar("T", bound=BaseModel)


class Confi:
    """
    Interface to create typed configuration entries
    """


    def __init__(self, prefix="") -> None:
        """

        Args:
            prefix (str, optional): Prefix to add to all env-var keys. Defaults to "".
        """
        self._prefix = prefix

    def _prefix_key(self, key):
        return f"{self._prefix}{key}"

    def str(self, key, default=undefined, description=None, **kwargs) -> str:
        return config(self._prefix_key(key), default=default, **kwargs)

    def int(self, key, default=undefined, description=None, **kwargs) -> int:
        return config(self._prefix_key(key), default=default, cast=int, **kwargs)

    def bool(self, key, default=undefined, description=None, **kwargs) -> bool:
        return config(self._prefix_key(key), default=default, cast=cast_boolean, **kwargs)

    def float(self, key, default=undefined, description=None, **kwargs) -> float:
        return config(self._prefix_key(key), default=default, cast=float, **kwargs)

    def list(self, key, default=undefined, sub_cast=text_type, delimiter=",", strip=string.whitespace, description=None, **kwargs) -> list:
        try:
            return config(self._prefix_key(key), cast=Csv(cast=sub_cast, delimiter=delimiter, strip=strip), **kwargs)
        except:
            if default is undefined:
                raise
            return default

    def model(self, key, model_type:T, default=undefined, description=None, **kwargs) -> T:
        """
        Parse a config using a Pydantic model
        """
        return config(self._prefix_key(key), default=default, cast=cast_pydantic(model_type), **kwargs)

    def enum(self, key, enum_type: EnumT, default=undefined, description=None, **kwargs) -> EnumT:
        try:
            return config(self._prefix_key(key), default=default, cast=enum_type, **kwargs)
        except:
            if default is undefined:
                raise
            return default

    def private_key(
        self,
        key: str,
        default: Any = undefined,
        description: str = None,
        key_format: Optional[EncryptionKeyFormat] = None,
        passphrase: Optional[str] = None,
        **kwargs
    ) -> Optional[PrivateKey]:
        """
        parse a cryptographic private key from env vars
        """
        cast_key = partial(cast_private_key, key_format=key_format, passphrase=passphrase)
        return config(self._prefix_key(key), default=default, cast=cast_key, **kwargs)

    def public_key(
        self,
        key: str,
        default: Any = undefined,
        description: str = None,
        key_format: Optional[EncryptionKeyFormat] = None,
        **kwargs
    ) -> Optional[PublicKey]:
        """
        parse a cryptographic public key from env vars
        """
        cast_key = partial(cast_public_key, key_format=key_format)
        return config(self._prefix_key(key), default=default, cast=cast_key, **kwargs)


# default parser
confi = Confi()
