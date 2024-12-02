from opal_common.logger import logger


def post_fork(server, worker):
    """This hook takes effect if we are using gunicorn to run OPAL."""
    pass


def when_ready(server):
    try:
        import opal_server.scopes.task
    except ImportError:
        # Not opal server
        return

    opal_server.scopes.task.ScopesPolicyWatcherTask.preload_scopes()
    logger.warning("Finished pre loading scopes...")
