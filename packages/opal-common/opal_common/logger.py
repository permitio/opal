import logging
import sys

from loguru import logger
from opal_common.config import opal_common_config
from opal_common.http_utils import redact_sensitive_text
from opal_common.logging_utils.filter import ModuleFilter
from opal_common.logging_utils.formatter import Formatter
from opal_common.logging_utils.intercept import InterceptHandler
from opal_common.logging_utils.scrubbing import CredentialScrubbingStream
from opal_common.logging_utils.thirdparty import hijack_uvicorn_logs
from opal_common.monitoring.apm import fix_ddtrace_logging


def _scrub_record_message(record):
    """loguru patcher: mask credentials (URL userinfo, sensitive query params,
    Authorization header values, Bearer/Basic tokens) in every record's message
    and in its top-level ``str`` extra values before it reaches any sink.

    The extra values matter because loguru also stores every keyword argument
    of a log call in ``record["extra"]``, which a ``serialize=True`` sink
    dumps even when the message does not reference it.

    Runs once per record (order-independent across sinks), so it also protects
    the optional rotating file sink, which is path-based and cannot be
    stream-wrapped. The stream sink is *additionally* wrapped with
    ``CredentialScrubbingStream`` to scrub rendered exception tracebacks and
    non-``str`` extra values, which this pass does not touch.
    """
    message = record.get("message")
    if message:
        record["message"] = redact_sensitive_text(message)
    extra = record.get("extra")
    if extra:
        for key, value in extra.items():
            if isinstance(value, str):
                extra[key] = redact_sensitive_text(value)


_logs_configured = False


def logs_configured() -> bool:
    """Whether configure_logs() has run in this process."""
    return _logs_configured


def configure_logs():
    """Takeover process logs and create a logger with Loguru according to the
    configuration."""
    global _logs_configured
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
    # Mask credentials in every record's message and str extras, for all sinks.
    logger.configure(patcher=_scrub_record_message)
    # Logger configuration
    pipe = sys.stderr if opal_common_config.LOG_PIPE_TO_STDERR else sys.stdout
    # Wrap the stream so credentials are masked in the final formatted record -
    # including third-party exception tracebacks (e.g. aiohttp rendering
    # ``https://user:pw@host?token=...``) that the model-layer redaction cannot
    # reach. Message/extra scrubbing for all sinks (incl. the rotating file sink,
    # which cannot be wrapped) is handled by the patcher above.
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
    _logs_configured = True


def get_logger(name=""):
    """Backward compatibility to old get_logger."""
    return logger
