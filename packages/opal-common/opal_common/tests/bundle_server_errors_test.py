"""Bundle server error handling: a non-JSON error page fails with the intended
error, and the auth header sent to the server never reaches the logs."""

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from loguru import logger
from opal_common.tests.redaction_fixtures import capture_logs
from opal_common.utils import throw_if_bad_status_code

FAKE_KEY = "FAKE-KEY-123"


async def _html_bad_gateway(request: web.Request) -> web.Response:
    return web.Response(
        status=502, text="<html>502 Bad Gateway</html>", content_type="text/html"
    )


async def _json_error(request: web.Request) -> web.Response:
    return web.json_response({"error": "no such bundle"}, status=500)


async def _redirect_loop(request: web.Request) -> web.Response:
    raise web.HTTPFound(request.path)


def _server(handler) -> TestServer:
    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    return TestServer(app)


@pytest.mark.asyncio
async def test_bad_status_with_html_body_raises_value_error():
    async with _server(_html_bad_gateway) as server, aiohttp.ClientSession() as session:
        async with session.get(server.make_url("/bundle.tar.gz")) as response:
            with capture_logs() as logs:
                with pytest.raises(ValueError, match="unexpected response code"):
                    await throw_if_bad_status_code(
                        response, expected=[200], logger=logger
                    )

    assert "Unexpected response code 502: <html>502 Bad Gateway</html>" in logs.text[0]


@pytest.mark.asyncio
async def test_bad_status_with_json_body_logs_the_parsed_details():
    async with _server(_json_error) as server, aiohttp.ClientSession() as session:
        async with session.get(server.make_url("/bundle.tar.gz")) as response:
            with capture_logs() as logs:
                with pytest.raises(ValueError, match="500"):
                    await throw_if_bad_status_code(
                        response, expected=[200], logger=logger
                    )

    assert "Unexpected response code 500: {'error': 'no such bundle'}" in logs.text[0]


def _bundle_source(server: TestServer, tmp_path):
    # ApiPolicySource imports opal-server's config, which a client-only install lacks
    api_policy_source = pytest.importorskip("opal_common.sources.api_policy_source")
    return api_policy_source.ApiPolicySource(
        remote_source_url=str(server.make_url("")),
        local_clone_path=str(tmp_path / "clone"),
        token=FAKE_KEY,
        bundle_server_type=api_policy_source.PolicyBundleServerType.HTTP,
        policy_bundle_path=str(tmp_path / "bundle.tar.gz"),
    )


@pytest.mark.asyncio
async def test_bundle_fetch_connection_error_log_omits_auth_header(tmp_path):
    """A redirect loop fails with TooManyRedirects carrying the first request,
    whose repr renders the Authorization header sent to the bundle server."""
    async with _server(_redirect_loop) as server:
        source = _bundle_source(server, tmp_path)
        with capture_logs() as logs:
            with pytest.raises(aiohttp.TooManyRedirects) as exc_info:
                await source.fetch_policy_bundle_from_api_source(
                    str(server.make_url("")).rstrip("/"), FAKE_KEY
                )

    assert FAKE_KEY in repr(exc_info.value)  # what the log line must not render
    assert "server connection error: TooManyRedirects" in logs.combined
    assert FAKE_KEY not in logs.combined


@pytest.mark.asyncio
async def test_bundle_fetch_unexpected_error_log_omits_auth_header(tmp_path):
    async with _server(_html_bad_gateway) as server:
        source = _bundle_source(server, tmp_path)
        with capture_logs() as logs:
            with pytest.raises(ValueError):
                await source.fetch_policy_bundle_from_api_source(
                    str(server.make_url("")).rstrip("/"), FAKE_KEY
                )

    assert "unexpected server connection error: ValueError" in logs.combined
    assert FAKE_KEY not in logs.combined
