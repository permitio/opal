import asyncio
import json
import secrets
from typing import Tuple
from uuid import uuid4
import typer
from enum import Enum
from opal_common.schemas.security import AccessTokenRequest, PeerType, TokenDetails
from datetime import timedelta


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



def obtain_token(
        master_token: str,
        uri: str = typer.Option("http://localhost:7002", help="url of server to obtain the token from"),
        type:PeerType=PeerType("client"),
        ttl: Tuple[int, str] = typer.Option((365, "days"), help="Time-To-Live / experation for the token in `<int> <str>` e.g. `365 days`, or `1000000 milliseconds` "),
        claims:str=typer.Option("{}", help="claims to to include in the returned signed JWT as a JSON string", callback=lambda x:json.loads(x)),
        just_the_token:bool=typer.Option(True, help="Should the command return only the cryptographic token, or the full JSON object"),
        ):
    """
    Obtain a secret JWT (JSON-Web-Token) from the server, to be used by clients or data sources for authentication
    Using the master token (as assigned to the server as OPAL_AUTH_MASTER_TOKEN)
    """
    
    from aiohttp import ClientSession

    url = f"{uri}/token"
    ttl_number, ttl_unit = ttl
    ttl = timedelta(**{ttl_unit:ttl_number})

    async def fetch():
        async with ClientSession(headers={"Authorization": f"bearer {master_token}"}) as session:
            details = AccessTokenRequest(type=type, ttl=ttl, claims=claims).json()
            res = await session.post(url, data=details)
            data = await res.json()
            if just_the_token:
                return data["token"]
            else:
                return data

    res = asyncio.run(fetch())
    typer.echo(res)
