import asyncio
import json
import secrets
from datetime import timedelta
from enum import Enum
from typing import List, Optional, Tuple
from uuid import uuid4

import typer
from opal_common.schemas.data import DataSourceEntry, DataUpdate
from opal_common.schemas.security import AccessTokenRequest, PeerType


class SecretFormat(str, Enum):
    hex = "hex"
    bytes = "bytes"
    urlsafe = "urlsafe"


def generate_secret(
    size: int = typer.Option(32, help="size in bytes of the secret"),
    format: SecretFormat = SecretFormat.urlsafe,
):
    if format == SecretFormat.hex:
        res = secrets.token_hex(size)
    elif format == SecretFormat.bytes:
        res = repr(secrets.token_bytes(size))
    else:
        res = secrets.token_urlsafe(size)

    typer.echo(res)


def obtain_token(
    master_token: str = typer.Argument(
        ...,
        help="The master token secret the OPAL-server was initialized with",
        envvar="OPAL_MASTER_TOKEN",
    ),
    server_url: str = typer.Option(
        "http://localhost:7002", help="url of the OPAL-server to obtain the token from"
    ),
    type: PeerType = PeerType("client"),
    ttl: Tuple[int, str] = typer.Option(
        (365, "days"),
        help="Time-To-Live / experation for the token in `<int> <str>` e.g. `365 days`, or `1000000 milliseconds` ",
    ),
    claims: str = typer.Option(
        "{}",
        help="claims to to include in the returned signed JWT as a JSON string",
        callback=lambda x: json.loads(x),
    ),
    just_the_token: bool = typer.Option(
        True,
        help="Should the command return only the cryptographic token, or the full JSON object",
    ),
):
    """Obtain a secret JWT (JSON-Web-Token) from the server, to be used by
    clients or data sources for authentication Using the master token (as
    assigned to the server as OPAL_AUTH_MASTER_TOKEN)"""

    from aiohttp import ClientSession

    server_url = f"{server_url}/token"
    ttl_number, ttl_unit = ttl
    ttl = timedelta(**{ttl_unit: ttl_number})

    async def fetch():
        async with ClientSession(
            headers={"Authorization": f"bearer {master_token}"}
        ) as session:
            details = AccessTokenRequest(type=type, ttl=ttl, claims=claims).json()
            res = await session.post(
                server_url, data=details, headers={"content-type": "application/json"}
            )
            data = await res.json()
            if just_the_token:
                return data["token"]
            else:
                return data

    res = asyncio.run(fetch())
    typer.echo(res)


def publish_data_update(
    token: Optional[str] = typer.Argument(
        None,
        help="the JWT obtained from the server for authentication (see obtain-token command)",
        envvar="OPAL_CLIENT_TOKEN",
    ),
    server_url: str = typer.Option(
        "http://localhost:7002",
        help="url of the OPAL-server to send the update through",
    ),
    server_route: str = typer.Option(
        "/data/config", help="route in the server for update"
    ),
    reason: str = typer.Option("", help="The reason for the update"),
    entries: str = typer.Option(
        "[]",
        "--entries",
        "-e",
        help="Pass in the the DataUpdate entries as JSON",
        callback=lambda x: json.loads(x),
    ),
    src_url: str = typer.Option(
        None,
        help="[SINGLE-ENTRY-UPDATE] url of the data-source this update relates to, which the clients should approach",
    ),
    topics: List[str] = typer.Option(
        None,
        "--topic",
        "-t",
        help="[SINGLE-ENTRY-UPDATE] [List] topic (can several) for the published update (to be matched to client subscriptions)",
    ),
    data: str = typer.Option(
        None,
        help="[SINGLE-ENTRY-UPDATE] actual data to include in the update (if src_url is also supplied, it would be sent but not used)",
    ),
    src_config: str = typer.Option(
        "{}",
        help="[SINGLE-ENTRY-UPDATE] Fetching Config as JSON",
        callback=lambda x: json.loads(x),
    ),
    dst_path: str = typer.Option(
        "",
        help="[SINGLE-ENTRY-UPDATE] Path the client should set this value in its data-store",
    ),
    save_method: str = typer.Option(
        "PUT",
        help="[SINGLE-ENTRY-UPDATE] How the data should be saved into the give dst-path",
    ),
):
    """Publish a DataUpdate through an OPAL-server (indicated by --server_url).

    [SINGLE-ENTRY-UPDATE]     Send a single update DataSourceEntry via
    the --src-url, --src-config, --topics, --dst-path, --save-method
    must include --src-url to use this flow. [Multiple entries]     Set
    DataSourceEntires as JSON (via --entries)     if you include a
    single entry as well- it will be merged into the given JSON
    """
    from aiohttp import ClientResponse, ClientSession

    if not entries and not src_url:
        typer.secho(
            "You must provide either multiple entries (-e / --entries) or a single entry update (--src_url)",
            fg="red",
        )
        return

    if not isinstance(entries, list):
        typer.secho("Bad input for --entires was ignored", fg="red")
        entries = []

    entries: List[DataSourceEntry]

    # single entry update (if used, we ignore the value of "entries")
    if src_url is not None:
        entries = [
            DataSourceEntry(
                url=src_url,
                data=(None if data is None else json.loads(data)),
                topics=topics,
                dst_path=dst_path,
                save_method=save_method,
                config=src_config,
            )
        ]

    server_url = f"{server_url}{server_route}"
    update = DataUpdate(entries=entries, reason=reason)

    async def publish_update():
        headers = {"content-type": "application/json"}
        if token is not None:
            headers.update({"Authorization": f"bearer {token}"})
        async with ClientSession(headers=headers) as session:
            body = update.json()
            res = await session.post(server_url, data=body)
            return res

    async def get_response_text(res: ClientResponse):
        return await res.text()

    typer.echo(f"Publishing event:")
    typer.secho(f"{str(update)}", fg="cyan")
    res = asyncio.run(publish_update())

    if res.status == 200:
        typer.secho("Event Published Successfully", fg="green")
    else:
        typer.secho("Event publishing failed with status-code - {res.status}", fg="red")
        text = asyncio.run(get_response_text(res))
        typer.echo(text)


all_commands = [obtain_token, generate_secret, publish_data_update]
