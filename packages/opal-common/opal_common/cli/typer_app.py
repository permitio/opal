from .commands import all_commands
import typer


def get_typer_app():
    app = typer.Typer()
    for cmd in all_commands:
        app.command()(cmd)
    return app


