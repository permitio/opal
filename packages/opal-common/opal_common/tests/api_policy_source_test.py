import pytest
from opal_common.sources import api_policy_source
from opal_server.config import PolicyBundleServerType


class _Response:
    status = 304
    headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Session:
    def __init__(self, request):
        self.request = request

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, url, headers):
        self.request(url, headers)
        return _Response()


@pytest.mark.asyncio
async def test_custom_bundle_filename_is_used_for_request_and_aws_signature(
    monkeypatch, tmp_path
):
    requested = {}
    signed = {}

    def record_request(url, headers):
        requested["url"] = url
        requested["headers"] = headers

    def sign_request(token_id, token, host, path, region):
        signed["path"] = path
        return {"Authorization": "signed"}

    monkeypatch.setattr(
        api_policy_source,
        "ClientSession",
        lambda **kwargs: _Session(record_request),
    )
    monkeypatch.setattr(api_policy_source, "build_aws_rest_auth_headers", sign_request)
    source = api_policy_source.ApiPolicySource(
        remote_source_url="https://bucket.example/policies",
        local_clone_path=str(tmp_path / "repo"),
        bundle_server_type=PolicyBundleServerType.AWS_S3,
        token="secret",
        token_id="access-key",
        bundle_filename="team-a.tar.gz",
        policy_bundle_path=str(tmp_path / "bundle.tar.gz"),
    )

    await source.fetch_policy_bundle_from_api_source(
        source.remote_source_url, source.token
    )

    assert requested["url"] == "https://bucket.example/policies/team-a.tar.gz"
    assert signed["path"] == "/policies/team-a.tar.gz"
    assert requested["headers"]["Authorization"] == "signed"
