from typing import Callable, Dict, List

import click
import typer
from typer.main import Typer

from .types import ConfiEntry


def create_click_cli(confi_entries: Dict[str, ConfiEntry], callback: Callable):
    cli = callback
    for key, entry in confi_entries.items():
        option_kwargs = entry.get_cli_option_kwargs()
        # make the key fit cmd-style (i.e. kebab-case)
        adjusted_key = entry.key.lower().replace("_", "-")
        keys = [f"--{adjusted_key}", entry.key]
        # add flag if given (i.e '-t' option)
        if entry.flags is not None:
            keys.extend(entry.flags)
        # use lower case as the key, and as is (no prefix, and no case altering) as the name
        # see https://click.palletsprojects.com/en/7.x/options/#name-your-options
        cli = click.option(*keys, **option_kwargs)(cli)
    # pass context
    cli = click.pass_context(cli)
    # wrap in group
    cli = click.group(invoke_without_command=True)(cli)
    return cli


def get_cli_object_for_config_objects(
    config_objects: list,
    typer_app: Typer = None,
    help: str = None,
    on_start: Callable = None,
):
    # callback to save CLI results back to objects
    def callback(ctx, **kwargs):
        if callable(on_start):
            on_start(ctx, **kwargs)

        for key, value in kwargs.items():
            # find the confi-object which the key belongs to and ...
            for config_obj in config_objects:
                if key in config_obj.entries:
                    # ... update that object with the new value
                    setattr(config_obj, key, value)
                    config_obj._entries[key].value = value

    if help is not None:
        callback.__doc__ = help
    # Create a merged config-entires map
    entries = {}
    for config_obj in config_objects:
        entries.update(config_obj.entries)
    # convert to a click-cli group
    click_group = create_click_cli(entries, callback)
    # add the typer app into our click group
    if typer_app is not None:
        typer_click_object = typer.main.get_command(typer_app)
        # add the app commands directly to out click app
        for name, cmd in typer_click_object.commands.items():
            click_group.add_command(cmd, name)
    return click_group
