"""
Easy Python configuration interface built on top of python-decouple and click / typer.
Adding typing support and parsing with Pydantic and Enum.
"""

import inspect
from collections import OrderedDict
from typing import Callable, Dict, List,  Type, TypeVar, Optional, Any, Union
from functools import partial
from click.decorators import command
from pydantic import BaseModel
from decouple import config, Csv, text_type, undefined, UndefinedValueError
import string
import json

from typer import Typer
import typer

from .types import ConfiDelay, ConfiEntry, no_cast
from .cli import get_cli_object_for_config_objects


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
ValueT = TypeVar("ValueT")



        
             
class Confi:
    """
    Interface to create typed configuration entries
    """

    def __init__(self, prefix=None, is_model=True) -> None:
        """

        Args:
            prefix (str, optional): Prefix to add to all env-var keys. Defaults to self.ENV_PREFIX (which defaults to "").
            is_model (bool, optional): Should Confi.<type> return a ConfiEntry (the default, True) or should it evaluate env settings immediately and return a value (False)
        """
        self._is_model = is_model
        self._prefix = prefix
        # entries to be evaluated
        self._entries: Dict[str, ConfiEntry] = OrderedDict()
        # delayed entries to be evaluated (instead of being referenced by self._entries)
        self._delayed_entries: Dict[str, ConfiDelay] = OrderedDict()
        # entries with delayed defaults (in addition to being referenced by self._entries)
        self._delayed_defaults: Dict[str, ConfiEntry] = OrderedDict()
 
        # eval class entries into values (by order of defintion - same order as in the config class lines)
        for name, entry in inspect.getmembers(self):

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
            default: ConfiDelay =  entry.default
            setattr(self, name, default.eval(self))       

        self.on_load()
        self._is_model = is_model

    @property
    def entries(self):
        return self._entries

    def _prefix_key(self, key):
        prefix = self._prefix
        return f"{prefix}{key}"

    def _eval_and_save_entry(self, name:str, entry:ConfiEntry):
        value = self._eval_entry(entry)
        setattr(self, name, value)
        return value

    def _eval_entry(self, entry:ConfiEntry):
        whole_key = self._prefix_key(entry.key)
        res = self._evaluate(whole_key,entry.default,entry.cast,**entry.kwargs)
        return res
        
    def _process(self, key, default=undefined, description=None, cast=no_cast, type:ValueT=str, **kwargs) -> Union[ValueT, ConfiEntry]:
        if self._is_model:
            return ConfiEntry(key, default,description, cast, type, **kwargs)
        else:
            whole_key = self._prefix_key(key)
            return self._evaluate(whole_key, default, cast, **kwargs)

    def _evaluate(self, key, default=undefined, cast=no_cast, **kwargs):
        try:
            res = config(key, default=default, cast=cast, **kwargs)
        except:
            if default is undefined:
                raise
            return default
        return res

    def __repr__(self) -> str:
        return json.dumps({k:str(v.value) for k,v in self.entries.items()},indent=2, sort_keys=True)

    def get_cli_object(self, config_objects:List["Confi"]=None, typer_app:Typer=None, help=None):
        if config_objects is None:
            config_objects = []
        config_objects.append(self)
        return get_cli_object_for_config_objects(config_objects, typer_app=typer_app, help=help)

    def cli(self,config_objects:List["Confi"]=None, typer_app:Typer=None, help=None):
        """
        Run a command-line-interface based on this configuration set, other config sets, and s typer cli app

        Args:
            config_objects (List[Confi, optional): additional config objects to share the CLI with this one. Defaults to None.
            typer_app (Typer, optional): A typer cli app with commands to expose to the CLI. Defaults to None.
        """
        self.get_cli_object(config_objects, typer_app=typer_app, help=help)()


    def on_load(self):
        """
        Callback called upon configuration load
        Add dynamic values you want set here (i.e. values which are based on other values)
        """
        pass

    def __setattr__(self, name: str, value: Any) -> None:
        """
            Make sure value updates are saved in internal entries as well 
        """
        super().__setattr__(name, value)
        # update entry as well (to sync with CLI, etc. )
        if not name.startswith("_") and name in self._entries:
            self._entries[name].value = value

    def delay(self, value):
        return ConfiDelay(value)

    # -- parser setters --

    def str(self, key, default=undefined, description=None, **kwargs) -> str:
        return self._process(key, description=description, default=default, type=str, **kwargs)

    def int(self, key, default=undefined, description=None, **kwargs) -> int:
        return self._process(key, description=description, default=default, cast=int, type=int, **kwargs)

    def bool(self, key, default=undefined, description=None, **kwargs) -> bool:
        return self._process(key, description=description, default=default, cast=cast_boolean, type=bool, **kwargs)

    def float(self, key, default=undefined, description=None, **kwargs) -> float:
        return self._process(key, description=description, default=default, cast=float, type=float, **kwargs)

    def list(self, key, default=undefined, sub_cast=text_type, delimiter=",", strip=string.whitespace, description=None, **kwargs) -> list:
        return self._process(key, default=default, description=description, cast=Csv(cast=sub_cast, delimiter=delimiter, strip=strip), type=list, **kwargs)

    def model(self, key, model_type:T, default=undefined, description=None, **kwargs) -> T:
        """
        Parse a config using a Pydantic model
        """
        return self._process(key, description=description, default=default, cast=cast_pydantic(model_type),type=model_type, **kwargs)

    def enum(self, key, enum_type: EnumT, default=undefined, description=None, **kwargs) -> EnumT:
        return self._process(key, description=description, default=default, cast=enum_type, type=enum_type, **kwargs)

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
        return self._process(key, description=description, default=default, cast=cast_key,type=PrivateKey, **kwargs)

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
        return self._process(key, description=description, default=default, cast=cast_key,type=PublicKey, **kwargs)


# default parser
confi = Confi()


