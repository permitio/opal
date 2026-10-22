from opal_common.logger import configure_logs, logger


def post_fork(server, worker):
    """This hook takes effect if we are using gunicorn to run OPAL."""
    pass


def when_ready(server):
    # This runs in the gunicorn MASTER, before any worker configured logging.
    # Without configure_logs() the master logs with loguru's defaults (DEBUG
    # level, plaintext, diagnose=True, no credential scrubbing) while the
    # scopes preload logs per-scope git chatter and git errors that can carry
    # the remote URL and its auth. Called before the import so nothing the
    # import might log reaches the default handler either. It also routes
    # stdlib logging (third-party libraries) into the same configured sink.
    configure_logs()

    try:
        import opal_server.scopes.task
    except ImportError:
        # Not opal server
        return

    opal_server.scopes.task.ScopesPolicyWatcherTask.preload_scopes()
    logger.warning("Finished pre loading scopes...")
