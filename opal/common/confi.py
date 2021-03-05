from typing import TypeVar, cast
from decouple import config, Csv, text_type, undefined, UndefinedValueError
import string

def cast_boolean(value):
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):        
        value = value.lower()
        if (value == "true"):
            return True
        elif value == "false":
            return False
        else:
            raise UndefinedValueError(f"{value} - is not a valid boolean")
    else:
        raise UndefinedValueError(f"{value} - is not a valid boolean")



T = TypeVar("T")


class Confi:

    def __init__(self) -> None:
        pass

    def str(self, key, default=undefined, **kwargs) -> str:
        return config(key, default=default, **kwargs)

    def int(self, key, default=undefined, **kwargs) -> int:
        return config(key, default=default, cast=int, **kwargs)

    def bool(self, key, default=undefined, **kwargs) -> bool:
        return config(key, default=default, cast=cast_boolean, **kwargs)

    def float(self, key, default=undefined, **kwargs) -> float:
        return config(key, default=default, cast=float, **kwargs)

    def list(self, key, default=undefined, sub_cast=text_type, delimiter=",", strip=string.whitespace, **kwargs) -> list:
        try:
            return config(key, cast=Csv(cast=sub_cast, delimiter=delimiter, strip=strip), **kwargs)
        except:
            if default is undefined:
                raise
            return default

    def enum(self, key, enum_type: T, default=undefined, **kwargs) -> T:
        try:
            return config(key, default=default, cast=enum_type, **kwargs)
        except:
            if default is undefined:
                raise
            return default

# default parser
confi = Confi()
