from typing import TypeVar
from decouple import config, Csv, text_type, undefined
import string


T = TypeVar("T")

class Confi:

    def __init__(self) -> None:
        pass

    def str(self, key, default=undefined, **kwargs)->str:
        return config(key, default=default, **kwargs)

    def int(self, key, default=undefined, **kwargs)->int:
        return config(key, default=default, cast=int, **kwargs)

    def float(self, key, default=undefined, **kwargs)->float:
        return config(key, default=default, cast=float, **kwargs)

    def list(self, key, default=undefined, sub_cast=text_type, delimiter=",", strip=string.whitespace, **kwargs)->list:
        try:
            return config(key, cast=Csv(cast=sub_cast,delimiter=delimiter, strip=strip), **kwargs)
        except:
            if default is undefined:
                raise
            return default

    def enum(self, key, enum_type:T, default=undefined, **kwargs)->T:
        try:
            return config(key, default=default, cast=enum_type, **kwargs) 
        except:
            if default is undefined:
                raise
            return default
    