import os

from opal_common.logger import logger


def post_fork(server, worker):
    """this hook takes effect if we are using gunicorn to run OPAL."""
    rookout_token = os.getenv("ROOKOUT_TOKEN", None)
    if not rookout_token:
        return

    service = os.getenv("ROOKOUT_SERVICE", "opal_server")
    env = os.getenv("ROOKOUT_ENV", "dev")
    user = os.getenv("ROOKOUT_USER", None)

    logger.info("Running Rookout...")
    labels = {"env": env, "service": service}
    if user is not None:
        labels.update({"user": user})

    import rook

    rook.start(token=rookout_token, labels=labels)


def when_ready(server):
    try:
        import opal_server.scopes.task
    except ImportError:
        # Not opal server
        return

    opal_server.scopes.task.ScopesPolicyWatcherTask.preload_scopes()
    logger.warning("Finished pre loading scopes...")
