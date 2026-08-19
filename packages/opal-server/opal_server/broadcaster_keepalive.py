"""TCP keepalive for the broadcaster's Postgres connections.

Why this exists: after a Multi-AZ failover of the broadcaster database the
listening (``LISTEN``) connection a worker holds to the OLD primary can stay
TCP-``ESTABLISHED`` but half-open — the old host is taken down without a
FIN/RST and a listening socket never writes, so nothing on the client side ever
notices. The reader task then waits forever on a dead socket: no reconnect, no
resync, and every client on that worker silently stops receiving fleet-wide
updates. The kernel's TCP keepalive is the cheapest detector: with the options
below an unresponsive peer is declared dead after ``idle + interval * count``
seconds (30 + 10 * 3 = 60 s by default), the socket errors, asyncpg reports the
connection closed, and the existing reconnect + resync path takes over.

Two hooks, both best-effort and fail-open (a keepalive that cannot be applied
is logged, never fatal):

* :func:`install_postgres_pool_keepalive` wraps the ``asyncpg.create_pool`` call
  the ``broadcaster`` library's Postgres backend makes, adding an ``init``
  callback that applies the options to EVERY pooled connection (listen and
  publish). It patches the name ``asyncpg`` *inside that one module only*, so no
  other asyncpg user in the process is affected. asyncpg exposes no client-side
  keepalive parameter (libpq's ``keepalives_*`` are not implemented), and the
  backend builds the pool itself, so this is the only seam.
* :func:`apply_keepalive_to_connection` is what the reconnecting broadcaster
  also calls on its own listening connection right after connecting, as a belt
  for a pool created before the hook was installed.
"""
import socket
from typing import Any, Optional

from opal_common.logger import logger

_POOL_HOOK_INSTALLED = False
_POOL_HOOK_TIMINGS: Optional[tuple] = None


def apply_tcp_keepalive(sock: Any, idle: int, interval: int, count: int) -> bool:
    """Enable TCP keepalive on ``sock`` with the given timings.

    Linux names the three timings ``TCP_KEEPIDLE`` / ``TCP_KEEPINTVL`` /
    ``TCP_KEEPCNT``; macOS spells idle ``TCP_KEEPALIVE``; platforms exposing
    none of them still get ``SO_KEEPALIVE`` with the kernel defaults. Returns
    True if ``SO_KEEPALIVE`` was set. Never raises: a socket that refuses an
    option (closed, not TCP, exotic platform) is reported as False.
    """
    if sock is None:
        return False
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except (OSError, AttributeError, TypeError):
        return False
    idle_opt = getattr(socket, "TCP_KEEPIDLE", None)
    if idle_opt is None:  # macOS spells the idle timer TCP_KEEPALIVE
        idle_opt = getattr(socket, "TCP_KEEPALIVE", None)
    for opt, value in (
        (idle_opt, idle),
        (getattr(socket, "TCP_KEEPINTVL", None), interval),
        (getattr(socket, "TCP_KEEPCNT", None), count),
    ):
        if opt is None or value is None or value <= 0:
            continue
        try:
            sock.setsockopt(socket.IPPROTO_TCP, opt, int(value))
        except (OSError, AttributeError, TypeError):
            # The flag itself is on; a timing the platform will not take just
            # leaves that one at the kernel default.
            continue
    return True


def _socket_of(conn: Any) -> Optional[Any]:
    """Dig the transport socket out of an asyncpg ``Connection`` or the pool's
    ``PoolConnectionProxy`` around it.

    Returns None when the shape is not what asyncpg currently exposes
    (private attributes — hence fail-open).
    """
    inner = getattr(conn, "_con", conn)
    transport = getattr(inner, "_transport", None)
    if transport is None:
        return None
    try:
        return transport.get_extra_info("socket")
    except Exception:
        return None


def apply_keepalive_to_connection(
    conn: Any, idle: int, interval: int, count: int, *, what: str = "connection"
) -> bool:
    """Apply :func:`apply_tcp_keepalive` to an asyncpg connection (or pool
    proxy); logs one INFO line per connection on success and one WARNING on
    failure."""
    sock = _socket_of(conn)
    ok = apply_tcp_keepalive(sock, idle, interval, count)
    if ok:
        logger.info(
            "Broadcaster {what}: TCP keepalive enabled (idle {idle}s, interval "
            "{interval}s, count {count}) — a half-open peer is declared dead after "
            "~{dead}s",
            what=what,
            idle=idle,
            interval=interval,
            count=count,
            dead=idle + interval * count,
        )
    else:
        logger.warning(
            "Broadcaster {what}: could not enable TCP keepalive (no socket on the "
            "transport or the platform refused it); half-open detection relies on "
            "BROADCAST_READER_SILENCE_TIMEOUT alone",
            what=what,
        )
    return ok


def install_postgres_pool_keepalive(idle: int, interval: int, count: int) -> bool:
    """Make every connection the broadcaster's Postgres pool creates carry TCP
    keepalive.

    Idempotent. Returns True if the hook is installed (now or earlier),
    False if the broadcaster library's Postgres backend is not
    importable (no asyncpg / different backend), in which case nothing
    is patched.
    """
    global _POOL_HOOK_INSTALLED, _POOL_HOOK_TIMINGS
    if _POOL_HOOK_INSTALLED:
        if _POOL_HOOK_TIMINGS != (idle, interval, count):
            logger.warning(
                "Broadcaster Postgres pool keepalive hook already installed with "
                "idle/interval/count {first}; ignoring the later request for {later} "
                "(first install wins for the process)",
                first=_POOL_HOOK_TIMINGS,
                later=(idle, interval, count),
            )
        return True
    try:
        from broadcaster._backends import postgres as pg_backend  # type: ignore
    except Exception:
        logger.debug(
            "broadcaster Postgres backend not importable; pool keepalive hook skipped"
        )
        return False
    real_asyncpg = pg_backend.asyncpg

    async def _init(conn):
        apply_keepalive_to_connection(
            conn, idle, interval, count, what="pooled connection"
        )

    class _KeepaliveAsyncpg:
        """Stand-in for the ``asyncpg`` name inside the backend module:

        forwards everything, and adds the keepalive ``init`` to
        ``create_pool``.
        """

        def __getattr__(self, name):
            return getattr(real_asyncpg, name)

        def create_pool(self, *args, **kwargs):
            kwargs.setdefault("init", _init)
            return real_asyncpg.create_pool(*args, **kwargs)

    pg_backend.asyncpg = _KeepaliveAsyncpg()
    _POOL_HOOK_INSTALLED = True
    _POOL_HOOK_TIMINGS = (idle, interval, count)
    logger.info(
        "Broadcaster Postgres pool: TCP keepalive hook installed (idle {idle}s, "
        "interval {interval}s, count {count})",
        idle=idle,
        interval=interval,
        count=count,
    )
    return True
