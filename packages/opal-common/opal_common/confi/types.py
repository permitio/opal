import inspect
from typing import Any, Callable, List, Type

from decouple import text_type, undefined


class FromStr:
    """Placeholder for values parsed from strings into more complex objects."""

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
        if hasattr(self._type, "__name__"):
            return f"<{self._type.__name__}>"
        else:
            return repr(self._type)


def no_cast(value):
    return value


class ConfiEntry:
    key: str
    type: Type
    default: Any
    description: str
    cast: Callable
    kwargs: dict
    flags: List[str]
    value: Any

    def __init__(
        self,
        key,
        default=undefined,
        description=None,
        cast=no_cast,
        type=str,
        index=-1,
        flags: List[str] = None,
        **kwargs,
    ) -> None:
        self.key = key
        # sorting index
        self.index = index
        self.default = default
        self.description = description
        self.cast = cast
        self.type = type
        self.kwargs = kwargs
        self.flags = flags
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
            res["help"] = self.description
        if self.default is not undefined:
            res["default"] = self.value if self.value is not undefined else self.default
            res["show_default"] = self.default
        return res


class ConfiDelay:
    """Delay loaded confi entry default values."""

    def __init__(self, value, index=-1) -> None:
        self._value = value
        # sorting index
        self.index = index

    @property
    def value(self):
        return self._value

    def eval(self, config=None):
        values = {k: v.value for k, v in config.entries.items()} if config else {}
        if isinstance(self._value, str):
            return self._value.format(**values)
        if callable(self._value):
            callargs = inspect.getcallargs(self._value)
            args = {k: values.get(k, undefined) for k, v in callargs.items()}
            return self._value(**args)

    def __repr__(self) -> str:
        try:
            return f"<Delayed {self.eval()}>"
        except:
            return f"<Delayed {self._value}>"
