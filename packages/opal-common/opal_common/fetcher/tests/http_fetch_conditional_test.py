"""HttpFetchProvider conditional requests (``conditional_requests``), with both
HTTP clients."""

from typing import List

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer
from opal_common.config import opal_common_config
from opal_common.fetcher.conditional import CacheValidators, NotModified, ValidatedData
from opal_common.fetcher.providers.http_fetch_provider import (
    HttpFetcherConfig,
    HttpFetchEvent,
    HttpFetchProvider,
)
from tenacity import stop_after_attempt

DATA = {"hello": "world"}
ETAG = '"v1"'
LAST_MODIFIED = "Wed, 05 Nov 2026 00:00:00 GMT"


@pytest.fixture(params=["aiohttp", "httpx"])
def http_client(request, monkeypatch):
    monkeypatch.setattr(
        opal_common_config, "HTTP_FETCHER_PROVIDER_CLIENT", request.param
    )
    return request.param


@pytest_asyncio.fixture
async def server():
    requests: List[dict] = []

    async def handle(request: web.Request) -> web.Response:
        requests.append(dict(request.headers))
        if request.headers.get("If-None-Match") == ETAG:
            # leaves out Last-Modified, as a 304 may
            return web.Response(status=304, headers={"ETag": ETAG})
        return web.json_response(
            DATA, headers={"ETag": ETAG, "Last-Modified": LAST_MODIFIED}
        )

    app = web.Application()
    app.router.add_route("*", "/data", handle)
    test_server = TestServer(app)
    await test_server.start_server()
    test_server.requests = requests
    yield test_server
    await test_server.close()


async def _fetch(server, validators=None, **config):
    event = HttpFetchEvent(
        url=str(server.make_url("/data")),
        config=HttpFetcherConfig(**config),
        validators=validators,
    )
    provider = HttpFetchProvider(event)
    # a 304 must not be treated as a failure (and retried)
    provider.set_retry_config({"stop": stop_after_attempt(1), "reraise": True})
    async with provider:
        return await provider.process(await provider.fetch())


@pytest.mark.asyncio
async def test_returns_data_with_validators(server, http_client):
    result = await _fetch(server, conditional_requests=True)

    assert isinstance(result, ValidatedData)
    assert result.data == DATA
    assert result.validators == CacheValidators(etag=ETAG, last_modified=LAST_MODIFIED)
    assert "If-None-Match" not in server.requests[0]


@pytest.mark.asyncio
async def test_not_modified(server, http_client):
    sent = CacheValidators(etag=ETAG, last_modified=LAST_MODIFIED)

    result = await _fetch(server, validators=sent, conditional_requests=True)

    assert server.requests[0]["If-None-Match"] == ETAG
    assert server.requests[0]["If-Modified-Since"] == LAST_MODIFIED
    assert isinstance(result, NotModified)
    # the validator the 304 left out is kept
    assert result.validators == sent


@pytest.mark.asyncio
async def test_off_by_default(server, http_client):
    result = await _fetch(server, validators=CacheValidators(etag=ETAG))

    assert result == DATA
    assert "If-None-Match" not in server.requests[0]


@pytest.mark.asyncio
async def test_get_only(server, http_client):
    result = await _fetch(
        server,
        validators=CacheValidators(etag=ETAG),
        conditional_requests=True,
        method="post",
    )

    assert result == DATA
    assert "If-None-Match" not in server.requests[0]
