import logging
import sys

from loguru import logger
from opal_common.config import opal_common_config
from opal_common.http_utils import redact_url_in_text
from opal_common.logging_utils.filter import ModuleFilter
from opal_common.logging_utils.formatter import Formatter
from opal_common.logging_utils.intercept import InterceptHandler
from opal_common.logging_utils.scrubbing import CredentialScrubbingStream
from opal_common.logging_utils.thirdparty import hijack_uvicorn_logs
from opal_common.monitoring.apm import fix_ddtrace_logging


def _scrub_record_message(record):
    """loguru patcher: scrub embedded URL credentials from every record's
    message before it reaches any sink.

    Runs once per record (order-independent across sinks), so it also protects
    the optional rotating file sink, which is path-based and cannot be
    stream-wrapped. The stream sink is *additionally* wrapped with
    ``CredentialScrubbingStream`` to scrub rendered exception tracebacks, which
    this message-only pass does not touch.
    """
    message = record.get("message")
    if message:
        record["message"] = redact_url_in_text(message)


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
    # Scrub credentialed URLs from every record's message, for all sinks.
    logger.configure(patcher=_scrub_record_message)
    # Logger configuration
    pipe = sys.stderr if opal_common_config.LOG_PIPE_TO_STDERR else sys.stdout
    # Wrap the stream so embedded URL credentials are scrubbed from the final
    # formatted record - including third-party exception tracebacks (e.g. aiohttp
    # rendering ``https://user:pw@host?token=...``) that the model-layer
    # redaction cannot reach. Message-level scrubbing for all sinks (incl. the
    # rotating file sink, which cannot be wrapped) is handled by the patcher above.
    logger.add(
        CredentialScrubbingStream(pipe),
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
