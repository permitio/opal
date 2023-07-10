import aiohttp
from fastapi import Response
from fastapi.encoders import jsonable_encoder


async def proxy_response(response: aiohttp.ClientResponse) -> Response:
    content = await response.text()
    return Response(
        content=content,
        status_code=response.status,
        headers=dict(response.headers),
        media_type="application/json",
    )


def exclude_none_fields(data):
    # remove default values from the pydatic model with a None value and also
    # convert the model to a valid JSON serializable type using jsonable_encoder
    return jsonable_encoder(data, exclude_none=True)
