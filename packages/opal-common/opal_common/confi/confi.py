"""Easy Python configuration interface built on top of python-decouple and
click / typer.

Adding typing support and parsing with Pydantic and Enum.
"""

import inspect
import json
import string
from collections import OrderedDict
from functools import partial, wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

from decouple import Csv, UndefinedValueError, config, text_type, undefined
from opal_common.authentication.casting import cast_private_key, cast_public_key
from opal_common.authentication.types import EncryptionKeyFormat, PrivateKey, PublicKey
from opal_common.logging.decorators import log_exception
from pydantic import BaseModel
from typer import Typer

from .cli import get_cli_object_for_config_objects
from .types import ConfiDelay, ConfiEntry, no_cast


def cast_boolean(value):
    """Parse an entry as a boolean.

    - all variations of "true" and 1 are treated as True
    - all variations of "false" and 0 are treated as False
    """
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        value = value.lower()
        if value == "true" or value == "1":
            return True
        elif value == "false" or value == "0":
            return False
        else:
            raise UndefinedValueError(f"{value} - is not a valid boolean")
    else:
        raise UndefinedValueError(f"{value} - is not a valid boolean")


def cast_pydantic(model: BaseModel):
    def cast_pydantic_by_model(value):
        if isinstance(value, str):
            return model.parse_raw(value)
        else:
            return model.parse_obj(value)

    return cast_pydantic_by_model


def ignore_confi_delay_cast(cast_func):
    """when we pass a ConfiDelay as the default to decouple, until this delayed
    default is evaluated by confi, there is no point in casting it.

    After a ConfiDelay is evaluated, the resulted value should be passed
    again to the cast method, and this time it will indeed be cast.
    """

    @wraps(cast_func)
    def wrapped_cast(value, *args, **kwargs):
        if isinstance(value, ConfiDelay):
            return value
        return cast_func(value, *args, **kwargs)

    return wrapped_cast


def load_conf_if_none(variable, conf):
    if variable is None:
        return conf
    else:
        return variable


EnumT = TypeVar("EnumT")
T = TypeVar("T", bound=BaseModel)
ValueT = TypeVar("ValueT")


class Confi:
    """Interface to create typed configuration entries."""

    def __init__(self, prefix=None, is_model=True) -> None:
        """

        Args:
            prefix (str, optional): Prefix to add to all env-var keys. Defaults to self.ENV_PREFIX (which defaults to "").
            is_model (bool, optional): Should Confi.<type> return a ConfiEntry (the default, True) or should it evaluate env settings immediately and return a value (False)
        """
        self._is_model = is_model
        self._prefix = prefix
        # counter of created entries (to track order)
        self._counter = 0
        # entries to be evaluated
        self._entries: Dict[str, ConfiEntry] = OrderedDict()
        # delayed entries to be evaluated (instead of being referenced by self._entries)
        self._delayed_entries: Dict[str, ConfiDelay] = OrderedDict()
        # entries with delayed defaults (in addition to being referenced by self._entries)
        self._delayed_defaults: Dict[str, ConfiEntry] = OrderedDict()

        # get members by creation order
        members = sorted(
            inspect.getmembers(self, self._is_entry), key=self._get_entry_index
        )
        # eval class entries into values (by order of defintion - same order as in the config class lines)
        for name, entry in members:
            # unwrap delayed entries
            if isinstance(entry, ConfiDelay):
                entry = entry.eval(self)

            if isinstance(entry, ConfiEntry):
                self._entries[name] = entry
                # save delayed
                if isinstance(entry.default, ConfiDelay):
                    self._delayed_defaults[name] = entry
                # eval, and save the value into the class instance
                value = self._eval_and_save_entry(name, entry)
                # save the value into the entry to be used as default for CLI
                entry.value = value

        # load (all calls inside should produce a real value)
        self._is_model = False

        # load delayed values:
        for name, entry in self._delayed_defaults.items():
            default: ConfiDelay = entry.default
            # but only if no value is set yet
            if entry.value == default or entry.value == undefined:
                setattr(self, name, entry.cast(default.eval(self)))

        self.on_load()
        self._is_model = is_model

    def _is_entry(self, entry):
        res = isinstance(entry, (ConfiEntry, ConfiDelay))
        return res

    def _get_entry_index(self, member: Tuple[str, ConfiEntry]):
        name, entry = member
        return entry.index

    @property
    def entries(self):
        return self._entries

    def _prefix_key(self, key):
        prefix = self._prefix
        return f"{prefix}{key}" if prefix is not None else key

    def _eval_and_save_entry(self, name: str, entry: ConfiEntry):
        value = self._eval_entry(entry)
        setattr(self, name, value)
        return value

    def _eval_entry(self, entry: ConfiEntry):
        whole_key = self._prefix_key(entry.key)
        res = self._evaluate(whole_key, entry.default, entry.cast, **entry.kwargs)
        return res

    def _process(
        self,
        key,
        default=undefined,
        description=None,
        cast=no_cast,
        type: ValueT = str,
        flags: List[str] = None,
        **kwargs,
    ) -> Union[ValueT, ConfiEntry]:
        if self._is_model:
            # create new entry
            res = ConfiEntry(
                key,
                default,
                description,
                cast,
                type,
                index=self._counter,
                flags=flags,
                **kwargs,
            )
            # track count for indexing
            self._counter += 1
            return res
        else:
            whole_key = self._prefix_key(key)
            return self._evaluate(whole_key, default, cast, **kwargs)

    def _evaluate(self, key, default=undefined, cast=no_cast, **kwargs):
        safe_cast_func = ignore_confi_delay_cast(cast)
        try:
            res = config(key, default=default, cast=safe_cast_func, **kwargs)
        except:
            if default is undefined:
                raise
            return default
        return res

    def __repr__(self) -> str:
        return json.dumps(
            {k: str(v.value) for k, v in self.entries.items()}, indent=2, sort_keys=True
        )

    def debug_repr(self) -> str:
        """repr() intended for debug purposes, since it runs repr() on each
        entry.value, it is more accurate than str(entry.value)"""
        repr_string = "{}(Confi):\n".format(self.__class__.__name__)
        items = list(self.entries.items())
        items.sort(key=lambda item: item[0])
        indent = " " * 4
        for key, entry in items:
            repr_string += f"{indent}{key}: {repr(entry.value)}\n"
        return repr_string

    def get_cli_object(
        self,
        config_objects: List["Confi"] = None,
        typer_app: Typer = None,
        help: str = None,
        on_start: Callable = None,
    ):

        if config_objects is None:
            config_objects = []
        config_objects.append(self)
        return get_cli_object_for_config_objects(
            config_objects, typer_app=typer_app, help=help, on_start=on_start
        )

    def cli(
        self,
        config_objects: List["Confi"] = None,
        typer_app: Typer = None,
        help: str = None,
        on_start: Callable = None,
    ):
        """Run a command-line-interface based on this configuration set, other
        config sets, and s typer cli app.

        Args:
            config_objects (List[Confi, optional): additional config objects to share the CLI with this one. Defaults to None.
            typer_app (Typer, optional): A typer cli app with commands to expose to the CLI. Defaults to None.
        """
        self.get_cli_object(
            config_objects, typer_app=typer_app, help=help, on_start=on_start
        )()

    def on_load(self):
        """Callback called upon configuration load Add dynamic values you want
        set here (i.e. values which are based on other values)"""
        pass

    def __setattr__(self, name: str, value: Any) -> None:
        """Make sure value updates are saved in internal entries as well."""
        super().__setattr__(name, value)
        # update entry as well (to sync with CLI, etc. )
        if not name.startswith("_") and name in self._entries:
            self._entries[name].value = value

    def delay(self, value):
        delayed_entry = ConfiDelay(value, index=self._counter)
        self._counter += 1
        return delayed_entry

    # -- parser setters --

    def str(self, key, default=undefined, description=None, **kwargs) -> str:
        return self._process(
            key, description=description, default=default, type=str, **kwargs
        )

    def int(self, key, default=undefined, description=None, **kwargs) -> int:
        return self._process(
            key, description=description, default=default, cast=int, type=int, **kwargs
        )

    def bool(self, key, default=undefined, description=None, **kwargs) -> bool:
        return self._process(
            key,
            description=description,
            default=default,
            cast=cast_boolean,
            type=bool,
            **kwargs,
        )

    def float(self, key, default=undefined, description=None, **kwargs) -> float:
        return self._process(
            key,
            description=description,
            default=default,
            cast=float,
            type=float,
            **kwargs,
        )

    def list(
        self,
        key,
        default=undefined,
        sub_cast=text_type,
        delimiter=",",
        strip=string.whitespace,
        description=None,
        **kwargs,
    ) -> list:
        return self._process(
            key,
            default=default,
            description=description,
            cast=Csv(cast=sub_cast, delimiter=delimiter, strip=strip),
            type=list,
            **kwargs,
        )

    def model(
        self, key, model_type: T, default=undefined, description=None, **kwargs
    ) -> T:
        """Parse a config using a Pydantic model."""
        return self._process(
            key,
            description=description,
            default=default,
            cast=cast_pydantic(model_type),
            type=model_type,
            **kwargs,
        )

    def enum(
        self, key, enum_type: EnumT, default=undefined, description=None, **kwargs
    ) -> EnumT:
        return self._process(
            key,
            description=description,
            default=default,
            cast=enum_type,
            type=enum_type,
            **kwargs,
        )

    @log_exception()
    def private_key(
        self,
        key: str,
        default: Any = undefined,
        description: str = None,
        key_format: Optional[EncryptionKeyFormat] = None,
        passphrase: Optional[str] = None,
        **kwargs,
    ) -> Optional[PrivateKey]:
        """parse a cryptographic private key from env vars."""
        cast_key = partial(
            cast_private_key, key_format=key_format, passphrase=passphrase
        )
        return self._process(
            key,
            description=description,
            default=default,
            cast=cast_key,
            type=PrivateKey,
            **kwargs,
        )

    @log_exception()
    def public_key(
        self,
        key: str,
        default: Any = undefined,
        description: str = None,
        key_format: Optional[EncryptionKeyFormat] = None,
        **kwargs,
    ) -> Optional[PublicKey]:
        """parse a cryptographic public key from env vars."""
        cast_key = partial(cast_public_key, key_format=key_format)
        return self._process(
            key,
            description=description,
            default=default,
            cast=cast_key,
            type=PublicKey,
            **kwargs,
        )


# default parser
confi = Confi()
