import logging
logger = logging.getLogger('data_fetcher')

def get_logger(name):
    return logger.getChild(name)