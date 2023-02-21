from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from socket import gethostname
from typing import Any, Optional

import ddtrace
import loguru
from loguru import logger
from loguru._defaults import env
from loguru._file_sink import FileSink
from opal_common.config import opal_common_config
from opal_common.logging.thirdparty import hijack_uvicorn_logs
from pydantic import BaseModel, ByteSize, FilePath, NonNegativeInt, parse_obj_as
from pydantic.json import pydantic_encoder

# quite down asyncio debug logs
asyncio_logger = logging.getLogger("asyncio")
asyncio_logger.setLevel(logging.INFO)

LOGURU_FORMAT: str = env(
    "LOGURU_FORMAT",
    str,
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "{process.id} | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)


class OPALLogSink(FileSink):
    def __init__(self, *args, **kwargs):
        super(OPALLogSink, self).__init__(*args, **kwargs)

    def write(self, message):
        r = message.record

        record = {
            "level": r.get("level").name,
            "logger": r.get("name"),
            "timestamp": r.get("time"),
            "message": r.get("message"),
            "location": {
                "function": r.get("function"),
                "file": r.get("file").path,
                "line": r.get("line"),
            },
            "process_id": r.get("process").id,
            "thread_id": r.get("thread").id,
        }

        record = record | get_ddtrace_info()
        super().write(json.dumps(record, default=pydantic_encoder) + "\n")


class InterceptHandler(logging.Handler):
    """This will cause log messages logged with the default python logging
    module propagate into loguru sinks.

    See https://loguru.readthedocs.io/en/stable/overview.html#entirely-
    compatible-with-standard-logging
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename in (logging.__file__,):
            if frame.f_back:
                frame = frame.f_back
                depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def format_record(record: dict) -> str:
    """format the string record with more context fields if present.

    :param record: the record to format
    :return:
    """
    format_string = LOGURU_FORMAT
    # add the request id if present
    format_string += "{exception}\n"
    return format_string


def get_ddtrace_info() -> dict[str, Any]:
    span = ddtrace.tracer.current_span()
    trace_id = None
    span_id = None
    if span:
        trace_id = span.trace_id
        span_id = span.span_id

    ddtrace_info: dict[str, str] = {}

    def set_if_value(d: dict[str, str], k: str, v: Optional[Any]):
        if v is not None:
            d[k] = v

    set_if_value(ddtrace_info, "dd.trace_id", trace_id)
    set_if_value(ddtrace_info, "dd.span_id", span_id)
    set_if_value(ddtrace_info, "dd.env", ddtrace.config.env)
    set_if_value(ddtrace_info, "dd.service", ddtrace.config.service)
    set_if_value(ddtrace_info, "dd.version", ddtrace.config.version)

    return ddtrace_info


def log_patcher(record: loguru.Record) -> None:
    """Adds fields to the logger record.

    :param record: The log record to manipulate
    :type record: loguru.Record
    """
    extra = record.get("extra", {})

    # render pydantic models to dicts
    for key in record.keys():
        value = record[key]
        if isinstance(value, BaseModel):
            record[key] = value.dict()

    # add datadog trace info
    extra["datadog"] = get_ddtrace_info()


def suffix_log_file_with_hostname(log_file: FilePath) -> str:
    # add service name is available, since logs from multiple service
    # are written to the same directory.
    if service_name := os.environ.get("DD_SERVICE"):
        log_filename = log_file.with_stem(
            f"{log_file.stem}-{service_name}-{gethostname()}"
        )
    else:
        log_filename = log_file.with_stem(f"{log_file.stem}-{gethostname()}")

    return str(log_filename)


def configure_logger(
    log_file: FilePath | None,
    log_file_rotation: ByteSize = parse_obj_as(ByteSize, "30 MB"),
    log_file_retention: NonNegativeInt = 1,
    prefix_intercept: tuple[str, ...] | None = None,
    level: str = "DEBUG",
) -> None:
    """Configure Loguru to log to stdout and optionally to a file."""
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq.connection").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    # DDTrace implements its own LogHandler leading to a fun deadlock
    logging.getLogger("ddtrace").propagate = False

    intercept_handler = InterceptHandler()
    hijack_uvicorn_logs(intercept_handler)
    logging.basicConfig(handlers=[intercept_handler], level=0)

    if prefix_intercept is not None and len(prefix_intercept) > 0:
        # extract loggers matches one of the prefixes given to intercept
        intercept_loggers = (
            logging.getLogger(name)
            for name in logging.root.manager.loggerDict
            if name.startswith(prefix_intercept)
        )

        # configure loggers matched with the prefix
        # to use the loguru interceptor and not propagate to prevent duplicate logs
        for _logger in intercept_loggers:
            _logger.handlers = [intercept_handler]
            _logger.propagate = False

    handlers = [{"sink": sys.stderr, "format": format_record, "level": level}]
    if log_file is not None:
        handlers.append(
            {
                "sink": OPALLogSink(
                    suffix_log_file_with_hostname(log_file),
                    rotation=log_file_rotation,
                    retention=log_file_retention,
                ),
                "serialize": True,
                "filter": {
                    "ddtrace": "WARNING",
                },
                "level": level,
            }
        )
    logger.configure(
        handlers=handlers,
        patcher=log_patcher,
    )


def configure_logs():
    log_file: Optional[Path] = None

    if opal_common_config.LOG_TO_FILE:
        log_file = Path(opal_common_config.LOG_FILE_PATH)

    configure_logger(
        log_file=log_file,
        log_file_rotation=opal_common_config.LOG_FILE_ROTATION,
        log_file_retention=opal_common_config.LOG_FILE_RETENTION,
        level=opal_common_config.LOG_LEVEL,
    )


def get_logger(name="") -> loguru.Logger:
    return logger
