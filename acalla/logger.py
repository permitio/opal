import collections
import inspect
import logging
import logging.config
import os
import threading

import structlog
from structlog import stdlib
from pydantic import BaseModel


PROD_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters":
        {
            "json": {
                "format": "%(message)s %(lineno)d %(pathname)s",
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            }
        },
    "handlers": {
        "json": {
            "class": "logging.StreamHandler",
            "formatter": "json"
        }
        },
    "loggers": {
        "": {
            "handlers": ["json"],
            "level": "INFO"
        }
        },
}


DEV_LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "default": {
            "level": "DEBUG",
            "()": "logging.StreamHandler",
        }
    },
    "loggers": {
        "": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": True
        }
    },
}


def is_dev():
    return "PROD_ENV" not in os.environ


default_log_level = "DEBUG" if is_dev() else "INFO"
log_level = os.environ.get("LOG_LEVEL", default_log_level)
LOGGING_CONFIG = DEV_LOGGING if is_dev() else PROD_LOGGING


def get_logger(logger_name):
    if logger_name is None:
        logger_name = inspect.currentframe().f_back.f_globals["__name__"]
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    return structlog.wrap_logger(logger)


def _add_thread_info(logger, method_name, event_dict):  # pylint: disable=unused-argument
    thread = threading.current_thread()
    event_dict["thread_id"] = thread.ident
    event_dict["thread_name"] = thread.name
    return event_dict


def _render_models(logger, method_name, event_dict):
    return {k: v.dict() if isinstance(v, BaseModel) else v for k, v in event_dict.items()}


def _order_keys(logger, method_name, event_dict):  # pylint: disable=unused-argument
    return collections.OrderedDict(sorted(event_dict.items(), key=lambda item: (item[0] != "event", item)))


logging.config.dictConfig(LOGGING_CONFIG)
processors_list = [
    # This performs the initial filtering, so we don't
    # evaluate e.g. DEBUG when unnecessary
    stdlib.filter_by_level,
    _add_thread_info,
    # Adds logger=module_name (e.g __main__)
    # Adds level=info, debug, etc.
    structlog.stdlib.add_log_level,
    # Performs the % string interpolation as expected
    structlog.stdlib.PositionalArgumentsFormatter(True),
    # Include the stack when stack_info=True
    structlog.processors.StackInfoRenderer(),
    # Include the exception when exc_info=True
    # e.g log.exception() or log.warning(exc_info=True)'s behavior
    structlog.processors.format_exc_info,
    # add the logger name
    structlog.stdlib.add_logger_name,
]
if not is_dev():
    processors_list = processors_list + [
        _order_keys,
        structlog.processors.JSONRenderer()  # in prod, render to json
    ]
else:
    processors_list = processors_list + [
        _order_keys,
        # renders to console (stdout)
        structlog.dev.ConsoleRenderer(repr_native_str=True)
    ]

if not structlog.is_configured():
    structlog.configure_once(
        context_class=dict,
        logger_factory=stdlib.LoggerFactory(),
        wrapper_class=stdlib.BoundLogger,
        processors=processors_list,
    )

logger = get_logger("SDK")