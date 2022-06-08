from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opal_common.config import opal_common_config
from opal_common.logger import logger
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str


def get_response() -> JSONResponse:
    error = ErrorResponse(error="Uncaught server exception")
    json_error = jsonable_encoder(error.dict())
    return JSONResponse(
        content=json_error, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def register_default_server_exception_handler(app: FastAPI):
    """Registers a default exception handler for HTTP 500 exceptions.

    Since fastapi does not include CORS headers by default in 500
    exceptions, we need to include them manually. Otherwise the frontend
    cries on the wrong issue.
    """

    @app.exception_handler(status.HTTP_500_INTERNAL_SERVER_ERROR)
    async def default_server_exception_handler(request: Request, exception: Exception):
        response = get_response()
        logger.exception("Uncaught server exception: {exc}", exc=exception)

        # Since the CORSMiddleware is not executed when an unhandled server exception
        # occurs, we need to manually set the CORS headers ourselves if we want the FE
        # to receive a proper JSON 500, opposed to a CORS error.
        # Setting CORS headers on server errors is a bit of a philosophical topic of
        # discussion in many frameworks, and it is currently not handled in FastAPI.
        # See dotnet core for a recent discussion, where ultimately it was
        # decided to return CORS headers on server failures:
        # https://github.com/dotnet/aspnetcore/issues/2378
        origin = request.headers.get("origin")

        if origin:
            # Have the middleware do the heavy lifting for us to parse
            # all the config, then update our response headers
            cors = CORSMiddleware(
                app=app,
                allow_origins=opal_common_config.ALLOWED_ORIGINS,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

            # Logic directly from Starlette's CORSMiddleware:
            # https://github.com/encode/starlette/blob/master/starlette/middleware/cors.py#L152

            response.headers.update(cors.simple_headers)
            has_cookie = "cookie" in request.headers

            # If request includes any cookie headers, then we must respond
            # with the specific origin instead of '*'.
            if cors.allow_all_origins and has_cookie:
                response.headers["Access-Control-Allow-Origin"] = origin

            # If we only allow specific origins, then we have to mirror back
            # the Origin header in the response.
            elif not cors.allow_all_origins and cors.is_allowed_origin(origin=origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers.add_vary_header("Origin")

        return response


def configure_cors_middleware(app: FastAPI):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=opal_common_config.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def configure_middleware(app: FastAPI):
    register_default_server_exception_handler(app)
    configure_cors_middleware(app)
