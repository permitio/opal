from logging.config import dictConfig
def hijack_uvicorn_logs():
    # Intercept future UVICORN
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
    # force existing UVICORN logging
    dictConfig(LOGGING_CONFIG)


    
