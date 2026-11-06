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
    """True if the URI's password carries a ``%`` character.

    Consumers of ``OPAL_BROADCAST_URI`` percent-decode the credentials
    (asyncpg has decoded the DSN user info since asyncpg#472). A ``%``
    therefore always means "escape sequence" to the driver, never a literal
    percent. The two readings are syntactically indistinguishable in the URI
    itself (``%071`` decodes whether the operator meant a control character
    or a literal ``%071``), so any ``%`` in the password is worth a startup
    pointer to the escaping contract — the silent mangling behind
    permitio/opal#584, whose only visible symptom was client websockets
    dropped right after they opened.
    """
    try:
        user_info = urlsplit(uri).netloc.rpartition("@")[0]
    except ValueError:  # e.g. unmatched brackets in a malformed URI
        return False
    return "%" in user_info.partition(":")[2]


def warn_on_unescaped_percent_in_uri(uri: str) -> None:
    """Log a pointer when ``uri``'s password looks like issue #584's trap.

    A raw ``%`` in the password (e.g. ``bnvcGy1pU%071lS``) is decoded as a
    percent-escape before it reaches the backbone: ``bnvcGy1pU%071lS``
    arrives at Postgres as ``bnvcGy1pU\\x071lS`` and authentication fails,
    with the broadcaster's connection error never surfacing in the log.
    Writing the password URI-escaped (``quote(password)`` ->
    ``bnvcGy1pU%25071lS``) reaches the backbone byte-for-byte.
    """
    if not uri_has_percent_escapes(uri):
        return
    logger.warning(
        "The password in the broadcast URI contains a % character. The URI's "
        "user info is percent-decoded before reaching the backbone "
        "(asyncpg#472), so a literal % in the password must be written "
        "escaped as %25 (e.g. via urllib.parse.quote); if the password is "
        "already escaped it reaches the backbone unchanged. An unescaped % "
        "silently breaks backbone authentication with no further log output "
        "(permitio/opal#584)."
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
