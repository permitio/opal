from urllib.parse import urlsplit

from fastapi_websocket_pubsub import PubSubClient, Topic
from opal_common.confi.confi import load_conf_if_none
from opal_common.logger import logger
from opal_common.topics.publisher import (
    ClientSideTopicPublisher,
    PeriodicPublisher,
    ServerSideTopicPublisher,
    TopicPublisher,
)
from opal_common.utils import get_authorization_header
from opal_server.config import opal_server_config


def uri_has_percent_escapes(uri: str) -> bool:
    """Return True if the URI password contains a ``%`` character.

    Broadcast URI drivers (such as asyncpg) percent-decode the DSN user info,
    meaning a ``%`` in the password is always interpreted as an escape
    sequence rather than a literal percent character.
    """
    try:
        user_info = urlsplit(uri).netloc.rpartition("@")[0]
    except ValueError:
        return False
    return "%" in user_info.partition(":")[2]


def warn_on_unescaped_percent_in_uri(uri: str) -> None:
    """Log a startup warning when ``uri`` has a ``%`` in its password.

    An unescaped ``%`` in a broadcast URI password (e.g. ``bnvcGy1pU%071lS``)
    is percent-decoded before reaching Postgres, corrupting the password and
    causing broadcast authentication to fail silently while dropping client
    websocket connections (permitio/opal#584).
    """
    if not uri_has_percent_escapes(uri):
        return
    logger.warning(
        "The password in the broadcast URI contains a % character. The URI "
        "user info is percent-decoded before reaching the broadcast backbone "
        "(asyncpg#472), so a literal % in the password must be percent-encoded "
        "as %25 (e.g. via urllib.parse.quote). An unescaped % causes backbone "
        "authentication to fail and drops client connections (permitio/opal#584)."
    )


def setup_publisher_task(
    server_uri: str = None,
    server_token: str = None,
) -> TopicPublisher:
    server_uri = load_conf_if_none(
        server_uri,
        opal_server_config.OPAL_WS_LOCAL_URL,
    )
    server_token = load_conf_if_none(
        server_token,
        opal_server_config.OPAL_WS_TOKEN,
    )
    return ClientSideTopicPublisher(
        client=PubSubClient(
            additional_headers=[get_authorization_header(server_token)]
        ),
        server_uri=server_uri,
    )


def setup_broadcaster_keepalive_task(
    publisher: ServerSideTopicPublisher,
    time_interval: int,
    topic: Topic = "__broadcast_session_keepalive__",
) -> PeriodicPublisher:
    """A periodic publisher with the intent to trigger messages on the
    broadcast channel, so that the session to the backbone won't become idle
    and close on the backbone end."""
    return PeriodicPublisher(
        publisher, time_interval, topic, task_name="broadcaster keepalive task"
    )
