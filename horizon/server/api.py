import aiohttp

from fastapi import APIRouter, status, Request, HTTPException
from horizon.config import POLICY_SERVICE_URL
from horizon.utils import proxy_response


HTTP_GET = "GET"
HTTP_DELETE = "DELETE"
HTTP_POST = "POST"
HTTP_PUT = "PUT"
HTTP_PATCH = "PATCH"

ALL_METHODS = [
    HTTP_GET,
    HTTP_DELETE,
    HTTP_POST,
    HTTP_PUT,
    HTTP_PATCH,
]

router = APIRouter()


@router.api_route("/sdk/{path:path}", methods=ALL_METHODS)
async def sdk_proxy(path: str, request: Request):
    """
    this one route proxies sdk route from the backend.
    obviously this is a very stupid route with no caching, etc.
    but we will probably throw this and write the sidecar in Go anyways.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header is None:
        HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Must provide a bearer token!",
            headers={"WWW-Authenticate": "Bearer"}
        )
    headers = {"Authorization": auth_header}
    path = f"{POLICY_SERVICE_URL}/{path}"

    async with aiohttp.ClientSession() as session:
        if request.method == HTTP_GET:
            async with session.get(path, headers=headers) as backend_response:
                return await proxy_response(backend_response)

        if request.method == HTTP_DELETE:
            async with session.delete(path, headers=headers) as backend_response:
                return await proxy_response(backend_response)

        # these methods has data payload
        data = request.body

        if request.method == HTTP_POST:
            async with session.post(path, headers=headers, data=data) as backend_response:
                return await proxy_response(backend_response)

        if request.method == HTTP_PUT:
            async with session.put(path, headers=headers, data=data) as backend_response:
                return await proxy_response(backend_response)

        if request.method == HTTP_PATCH:
            async with session.patch(path, headers=headers, data=data) as backend_response:
                return await proxy_response(backend_response)

    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="This method is not supported"
    )
