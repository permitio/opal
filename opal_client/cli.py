import typer
import click

import os, sys

# Add parent path to use local src as package for tests
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.append(root_dir)

from opal_client.config import opal_client_config
from opal_common.config import opal_common_config


app = typer.Typer()

@app.command()
def run():
    """
    Run the client as a deamon 
    """
    typer.echo("Starting OPAL client")

@app.command()
def print_config():
    """
    To test config values, print the configuration parsed from ENV and CMD
    """
    typer.echo("Printing configuration values") 
    typer.echo(str(opal_client_config))   
    typer.echo(str(opal_common_config))   


cli_header = """\b
OPAL-CLIENT
Open-Policy Administration Layer - client\b\f"""

cli_docs="""\b
Config:
 - Use env-vars (same as cmd options) but uppercase and with "_" instead of "-"; all prefixed with "OPAL_"
 - Use command line options as detailed by '--help'
 - Use .env or .ini files                                                                                                                                                                              
\b
"""

if __name__ == "__main__":
   typer.secho(cli_header, bold=True, fg=typer.colors.MAGENTA)   
   opal_client_config.cli([opal_common_config], typer_app=app, help=cli_docs)







