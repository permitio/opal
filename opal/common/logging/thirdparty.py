def hijack_uvicorn_logs():
    from uvicorn.config import LOGGING_CONFIG
    LOGGING_CONFIG["handlers"] =  {
            "default": {
                "formatter": "default",
                "class": "opal.common.logging.intercept.InterceptHandler",
            },
            "access": {
                "formatter": "access",
                "class": "opal.common.logging.intercept.InterceptHandler",
            },
        }
