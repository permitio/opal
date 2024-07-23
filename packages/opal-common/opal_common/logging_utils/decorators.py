import functools
import logging


def log_exception(logger=logging.getLogger(), rethrow=True):
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(e)
                if rethrow:
                    raise

        return wrapper

    return deco
