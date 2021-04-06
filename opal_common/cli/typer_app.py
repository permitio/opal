from .commands import generate_secret, obtain_token
import typer


def get_typer_app():
    app = typer.Typer()
    commands = [generate_secret, obtain_token]
    for cmd in commands:
        app.command()(cmd)
    return app


