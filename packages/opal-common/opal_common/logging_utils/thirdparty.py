import logging


def hijack_uvicorn_logs(intercept_handler: logging.Handler):
    """Uvicorn loggers are configured to use special handlers.

    Adding an intercept handler to the root logger manages to intercept logs from uvicorn, however, the log messages are duplicated.
    This is happening because uvicorn loggers are propagated by default - we get a log message once for the "uvicorn" / "uvicorn.error"
    logger and once for the root logger). Another stupid issue is that the "uvicorn.error" logger is not just for errors, which is confusing.

    This method is doing 2 things for each uvicorn logger:
    1) remove all existing handlers and replace them with the intercept handler (i.e: will be logged via loguru)
    2) cancel propagation - which will mean messages will not propagate to the root logger (which also has an InterceptHandler), fixing the duplication
    """
    # get loggers directly from uvicorn config - if they will change something - we will know.
    from uvicorn.config import LOGGING_CONFIG

    uvicorn_logger_names = list(LOGGING_CONFIG.get("loggers", {}).keys()) or [
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
    ]
    for logger_name in uvicorn_logger_names:
        logger = logging.getLogger(logger_name)
        logger.handlers = [intercept_handler]
        logger.propagate = False
