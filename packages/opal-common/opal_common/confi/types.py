import inspect
import re
from enum import Enum
from typing import Any, Callable, List, Type

import click
from decouple import text_type, undefined
from opal_common.logging_utils.errors import describe_validation_error
from pydantic import ValidationError

#: Entry keys treated as sensitive even when not flagged ``sensitive=True``.
SENSITIVE_KEY_PATTERN = re.compile(
    r"TOKEN|SECRET|PASSWORD|PASSPHRASE|API_KEY|PRIVATE_KEY|SSH_KEY", re.IGNORECASE
)
#: How a sensitive entry's value is shown in a printed config or ``--help``.
REDACTED = "<redacted>"


def holds_no_credential(value: Any) -> bool:
    """Unset, empty, flag and enum values (e.g. ``AUTH_PRIVATE_KEY_FORMAT``,
    caught by the name fallback) are shown even for a sensitive entry."""
    return (
        value is None
        or value is undefined
        or (isinstance(value, str) and not value)
        or isinstance(value, (bool, Enum))
    )


class FromStr:
    """Placeholder for values parsed from strings into more complex objects.

    On a ValueError while parsing a CLI option, click prints the rejected value
    itself (click < 8.2) or the error's str() - which for a pydantic error
    embeds the input. Errors that could carry the value are raised as
    ``click.BadParameter``, which click prints as given.
    """

    def __init__(self, type, cast, sensitive: bool = False):
        self._type = type
        self.cast = cast
        self._sensitive = sensitive

    def __call__(self, arg) -> Any:
        if arg is undefined:
            return undefined
        try:
            return self.cast(arg)
        except ValidationError as err:
            raise click.BadParameter(describe_validation_error(err)) from None
        except ValueError as err:
            if not self._sensitive:
                raise
            # e.g. a private key that does not load - click < 8.2 would print it
            raise click.BadParameter(
                f"could not be parsed ({type(err).__name__})"
            ) from None

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
    cast_from_json: Callable
    kwargs: dict
    flags: List[str]
    sensitive: bool
    value: Any

    def __init__(
        self,
        key,
        *,
        default=undefined,
        description=None,
        cast=no_cast,
        cast_from_json=no_cast,
        type=str,
        index=-1,
        flags: List[str] = None,
        sensitive: bool = False,
        **kwargs,
    ) -> None:
        self.key = key
        # sorting index
        self.index = index
        self.default = default
        self.description = description
        self.cast = cast
        self.cast_from_json = cast_from_json
        self.type = type
        self.kwargs = kwargs
        self.flags = flags
        # flagged explicitly, or named like a credential
        self.sensitive = sensitive or SENSITIVE_KEY_PATTERN.search(key) is not None
        self.value = undefined

    def get_cli_type(self):
        if self.type in {str, int, float, list, dict, bool}:
            return self.type
        else:
            return FromStr(self.type, self.cast, sensitive=self.sensitive)

    def get_cli_option_kwargs(self):
        res = {
            "type": self.get_cli_type(),
        }
        if self.description is not None:
            res["help"] = self.description
        if self.default is not undefined:
            res["default"] = self.value if self.value is not undefined else self.default
            res["show_default"] = self.default
            if self.sensitive and not holds_no_credential(self.default):
                # click renders a non-str show_default as the default it was given,
                # i.e. the value resolved from the environment.
                res["show_default"] = REDACTED
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
