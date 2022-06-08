import aiohttp
from fastapi import Response


async def proxy_response(response: aiohttp.ClientResponse) -> Response:
    content = await response.text()
    return Response(
        content=content,
        status_code=response.status,
        headers=dict(response.headers),
        media_type="application/json",
    )
