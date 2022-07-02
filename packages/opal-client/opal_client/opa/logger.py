import json
import logging
from enum import Enum
from typing import Optional

from opal_client.config import OpaLogFormat
from opal_client.logger import logger


def logging_level_from_string(level: str) -> int:
    """logger.log() requires an int logging level."""
    level = level.lower()
    if level == "info":
        return logging.INFO
    elif level == "critical":
        return logging.CRITICAL
    elif level == "fatal":
        return logging.FATAL
    elif level == "error":
        return logging.ERROR
    elif level == "warning" or level == "warn":
        return logging.WARNING
    elif level == "debug":
        return logging.DEBUG
    # default
    return logging.INFO


async def pipe_opa_logs(stream, logs_format: OpaLogFormat):
    """gets a stream of logs from the opa process, and logs it into the main
    opal log."""
    if logs_format == OpaLogFormat.NONE:
        return

    while True:
        line = await stream.readline()
        if not line:
            break
        try:
            log_line = json.loads(line)
            level = logging.getLevelName(
                logging_level_from_string(log_line.pop("level", "info"))
            )
            msg = log_line.pop("msg", None)

            logged = False
            if logs_format == OpaLogFormat.MINIMAL:
                logged = log_event_name(level, msg)
            elif logs_format == OpaLogFormat.HTTP:
                logged = log_formatted_http_details(level, msg, log_line)

            # always fall back to log the entire line
            if not logged or logs_format == OpaLogFormat.FULL:
                log_entire_dict(level, msg, log_line)
        except json.JSONDecodeError:
            logger.info(line)


def log_event_name(level: str, msg: Optional[str]) -> bool:
    if msg is not None:
        logger.log(level, "{msg: <20}", msg=msg)
        return True
    return False


def log_formatted_http_details(level: str, msg: Optional[str], log_line: dict) -> bool:
    method: Optional[str] = log_line.pop("req_method", None)
    path: Optional[str] = log_line.pop("req_path", None)
    status: Optional[int] = log_line.pop("resp_status", None)

    if msg is None or method is None or path is None:
        return False

    if status is None:
        format = "{msg: <20} <fg #999>{method} {path}</>"
        logger.opt(colors=True).log(level, format, msg=msg, method=method, path=path)
    else:
        format = "{msg: <20} <fg #999>{method} {path} -> {status}</>"
        logger.opt(colors=True).log(
            level, format, msg=msg, method=method, path=path, status=status
        )

    return True


def log_entire_dict(level: str, msg: Optional[str], log_line: dict):
    if msg is None:
        format = "<fg #999>{log_line}</>"
    else:
        format = "{msg: <20} <fg #bfbfbf>{log_line}</>"

    try:
        log_line = json.dumps(log_line)  # should be ok, originated in json
    except:
        pass  # fallback to dict
    logger.opt(colors=True).log(level, format, msg=msg, log_line=log_line)
    return True
