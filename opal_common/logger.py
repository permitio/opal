from loguru import logger
import logging
import sys
from .logging.intercept import InterceptHandler
from .logging.thirdparty import hijack_uvicorn_logs
from .logging.formatter import Formatter
from .logging.filter import ModuleFilter
from . import config


def configure_logs():
    """
    Takeover process logs and create a logger with Loguru according to the configuration
    """
    intercept_handler = InterceptHandler()
    formatter = Formatter()
    filter = ModuleFilter(include_list=config.LOG_MODULE_INCLUDE_LIST, exclude_list=config.LOG_MODULE_EXCLUDE_LIST)
    logging.basicConfig(handlers=[intercept_handler], level=0, force=True)
    if config.LOG_PATCH_UVICORN_LOGS:
        # Monkey patch UVICORN to use our logger
        hijack_uvicorn_logs()
    # Clean slate
    logger.remove()
    # Logger configuration
    logger.add(
        sys.stderr,
        filter=filter.filter,
        format=formatter.format,
        level=config.LOG_LEVEL,
        backtrace=config.LOG_TRACEBACK,
        diagnose=config.LOG_DIAGNOSE,
        colorize=config.LOG_COLORIZE,
    )
    # log to a file
    if config.LOG_TO_FILE:
        logger.add(
            config.LOG_FILE_PATH,
            compression=config.LOG_FILE_COMPRESSION,
            retention=config.LOG_FILE_RETENTION,
            rotation=config.LOG_FILE_ROTATION,
            serialize=config.LOG_FILE_SERIALIZE,
            level=config.LOG_FILE_LEVEL,
        )


def get_logger(name=""):
    """
    backward comptability to old get_logger
    """
    return logger


configure_logs()
