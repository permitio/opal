import aiohttp


def is_http_error_response(response: aiohttp.ClientResponse) -> bool:
    """HTTP 400 and above are considered error responses."""
    return response.status >= 400
