import secrets
import typer
from enum import Enum


class SecretFormat(str, Enum):
    hex = "hex"
    bytes = "bytes"
    urlsafe = "urlsafe"


def generate_secret(size: int = typer.Option(32, help="size in bytes of the secret"),
                    format: SecretFormat = SecretFormat.urlsafe):
    if format == SecretFormat.hex:
        res = secrets.token_hex(size)
    elif format == SecretFormat.bytes:   
        res = repr(secrets.token_bytes(size))
    else: 
        res = secrets.token_urlsafe(size)

    typer.echo(res)