import json
import logging

from opal_client.logger import logger

def logging_level_from_string(level: str) -> int:
    """
    logger.log() requires an int logging level
    """
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

async def pipe_opa_logs(stream):
    """
    gets a stream of logs from the opa process, and logs it into the main opal log.
    """
    while True:
        line = await stream.readline()
        if not line:
            break
        try:
            log_line = json.loads(line)
            msg = log_line.pop("msg", None)
            level = logging.getLevelName(logging_level_from_string(log_line.pop("level", "info")))
            if msg is not None:
                logger.log(level, msg, **log_line)
            else:
                logger.log(level, line)
        except json.JSONDecodeError:
            logger.info(line)