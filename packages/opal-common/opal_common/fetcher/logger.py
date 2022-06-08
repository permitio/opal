import logging

logger = logging.getLogger("opal.fetcher")


def get_logger(name):
    return logger.getChild(name)
