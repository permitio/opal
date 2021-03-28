import click
import uvicorn

from opal.common.confi_cli import options_from_confi




@click.group()
def cli():
    pass


@cli.command()
@options_from_confi()
def run(*args, **kwargs):
    # Opal client is loaded here on purpose to allow for configuration changes before the
    # config module is loaded.
    from opal.client.main import app
    uvicorn.run(app, port=9000)


@cli.command()
def command2():
    pass


if __name__ == "__main__":
    cli()
