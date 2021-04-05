
from typing import Any, Callable, Type
from decouple import  text_type, undefined


class FromStr:
    def __init__(self, type, cast):
        self._type = type
        self.cast = cast

    def __call__(self, arg) -> Any:
        if arg is not undefined:
            return self.cast(arg)
        else:
            return undefined

    @property
    def __name__(self) -> str:
        return f"<{self._type.__name__}>"

class ConfiEntry:
    key:str
    type: Type
    default: Any
    description:str
    cast:Callable
    kwargs: dict 
    value: Any

    def __init__(self, key, default=undefined, description=None, cast=text_type, type=str, **kwargs) -> None:
        self.key = key
        self.default = default
        self.description = description
        self.cast = cast
        self.type = type
        self.kwargs = kwargs
        self.value = undefined

    def get_cli_type(self):
        if self.type in {str, int, float, list, dict, bool}:
            return self.type
        else: 
            return FromStr(self.type, self.cast)

    def get_cli_option_kwargs(self):
        res = {
            "type": self.get_cli_type(),
        }
        if self.description is not None:
            res['help'] = self.description
        if self.default is not undefined:
            res['default'] = self.value if self.value is not undefined else self.default
            res['show_default'] = self.default
        return res
        
        
