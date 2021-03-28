import click
import os
from functools import partial
from importlib import reload

import opal.config.client.config as client_config


def options_from_confi():

    def decorator(f):
        for cli_key, params in client_config.confi.cli_options.items():
            env_key = params["env_key"]
            param_decls = (
                '--' + cli_key,
            )

            def callback(ctx, param, value, env_key):
                print(ctx, param, value)
                if value is not None:
                    os.environ[env_key] = str(value)
                    # TODO reload only once
                    reload(client_config)

            callback_with_envkey = partial(callback, env_key=env_key)
            attrs = dict(
                required=params["required"],
                type=str,
                callback=callback_with_envkey,
                help=params["description"] or f"Overrides environment variable {env_key}"
            )

            click.option(*param_decls, **attrs)(f)
        return f
    return decorator
