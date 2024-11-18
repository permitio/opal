import logging
import sys

from loguru import logger
from opal_common.config import opal_common_config
from opal_common.logging_utils.filter import ModuleFilter
from opal_common.logging_utils.formatter import Formatter
from opal_common.logging_utils.intercept import InterceptHandler
from opal_common.logging_utils.thirdparty import hijack_uvicorn_logs
from opal_common.monitoring.apm import fix_ddtrace_logging


def configure_logs():
    """Takeover process logs and create a logger with Loguru according to the
    configuration."""
    fix_ddtrace_logging()

    intercept_handler = InterceptHandler()
    formatter = Formatter(opal_common_config.LOG_FORMAT)
    filter = ModuleFilter(
        include_list=opal_common_config.LOG_MODULE_INCLUDE_LIST,
        exclude_list=opal_common_config.LOG_MODULE_EXCLUDE_LIST,
    )
    logging.basicConfig(handlers=[intercept_handler], level=0, force=True)

    if opal_common_config.LOG_PATCH_UVICORN_LOGS:
        # Monkey patch UVICORN to use our logger
        hijack_uvicorn_logs(intercept_handler)
    # Clean slate
    logger.remove()
    # Logger configuration
    logger.add(
        sys.stderr,
        filter=filter.filter,
        format=formatter.format,
        level=opal_common_config.LOG_LEVEL,
        backtrace=opal_common_config.LOG_TRACEBACK,
        diagnose=opal_common_config.LOG_DIAGNOSE,
        colorize=opal_common_config.LOG_COLORIZE,
        serialize=opal_common_config.LOG_SERIALIZE,
    )
    # log to a file
    if opal_common_config.LOG_TO_FILE:
        logger.add(
            opal_common_config.LOG_FILE_PATH,
            compression=opal_common_config.LOG_FILE_COMPRESSION,
            retention=opal_common_config.LOG_FILE_RETENTION,
            rotation=opal_common_config.LOG_FILE_ROTATION,
            serialize=opal_common_config.LOG_FILE_SERIALIZE,
            level=opal_common_config.LOG_FILE_LEVEL,
        )


def get_logger(name=""):
    """Backward compatibility to old get_logger."""
    return logger
