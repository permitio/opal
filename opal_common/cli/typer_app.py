from .commands import generate_secret
import typer


def get_typer_app():
    app = typer.Typer()
    app.command()(generate_secret)
    return app


