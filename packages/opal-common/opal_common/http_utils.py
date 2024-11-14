from typing import Union

import aiohttp
import httpx


def is_http_error_response(
    response: Union[aiohttp.ClientResponse, httpx.Response]
) -> bool:
    """HTTP 400 and above are considered error responses."""
    status: int = (
        response.status
        if isinstance(response, aiohttp.ClientResponse)
        else response.status_code
    )

    return status >= 400
