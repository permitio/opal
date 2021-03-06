from typing import TypeVar, cast
from pydantic import BaseModel
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

    def __init__(self) -> None:
        pass

    def str(self, key, default=undefined, description=None, **kwargs) -> str:
        return config(key, default=default, **kwargs)

    def int(self, key, default=undefined, description=None, **kwargs) -> int:
        return config(key, default=default, cast=int, **kwargs)

    def bool(self, key, default=undefined, description=None, **kwargs) -> bool:
        return config(key, default=default, cast=cast_boolean, **kwargs)

    def float(self, key, default=undefined, description=None, **kwargs) -> float:
        return config(key, default=default, cast=float, **kwargs)

    def list(self, key, default=undefined, sub_cast=text_type, delimiter=",", strip=string.whitespace, description=None, **kwargs) -> list:
        try:
            return config(key, cast=Csv(cast=sub_cast, delimiter=delimiter, strip=strip), **kwargs)
        except:
            if default is undefined:
                raise
            return default

    def json(self, key, value_type:T, default=undefined, description=None, **kwargs) -> T:       
        return config(key, default=default, cast=cast_pydantic(value_type), **kwargs)

    def enum(self, key, enum_type: EnumT, default=undefined, description=None, **kwargs) -> EnumT:
        try:
            return config(key, default=default, cast=enum_type, **kwargs)
        except:
            if default is undefined:
                raise
            return default

# default parser
confi = Confi()





