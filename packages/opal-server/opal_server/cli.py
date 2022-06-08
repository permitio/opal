import os
import sys

import typer
from click.core import Context
from fastapi.applications import FastAPI
from typer.main import Typer

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.append(root_dir)

from opal_common.cli.docs import MainTexts
from opal_common.cli.typer_app import get_typer_app
from opal_common.config import opal_common_config
from opal_common.corn_utils import run_gunicorn, run_uvicorn
from opal_server.config import opal_server_config

app = get_typer_app()


@app.command()
def run(engine_type: str = typer.Option("uvicron", help="uvicorn or gunicorn")):
    """Run the server as a deamon."""
    typer.echo(f"-- Starting OPAL Server (with {engine_type}) --")

    if engine_type == "gunicorn":
        app: FastAPI
        from opal_server.main import app

        run_gunicorn(
            app,
            opal_server_config.SERVER_WORKER_COUNT,
            host=opal_server_config.SERVER_HOST,
            port=opal_server_config.SERVER_PORT,
        )
    else:
        run_uvicorn(
            "opal_server.main:app",
            workers=opal_server_config.SERVER_WORKER_COUNT,
            host=opal_server_config.SERVER_HOST,
            port=opal_server_config.SERVER_PORT,
        )


@app.command()
def print_config():
    """To test config values, print the configuration parsed from ENV and
    CMD."""
    typer.echo("Printing configuration values")
    typer.echo(str(opal_server_config))
    typer.echo(str(opal_common_config))


def cli():
    main_texts = MainTexts("💎 OPAL-SERVER 💎", "server")

    def on_start(ctx: Context, **kwargs):
        if ctx.invoked_subcommand is None or ctx.invoked_subcommand == "run":
            typer.secho(main_texts.header, bold=True, fg=typer.colors.MAGENTA)
        if ctx.invoked_subcommand is None:
            typer.echo(ctx.get_usage())
            typer.echo(main_texts.docs)

    opal_server_config.cli(
        [opal_common_config], typer_app=app, help=main_texts.docs, on_start=on_start
    )


if __name__ == "__main__":
    cli()
