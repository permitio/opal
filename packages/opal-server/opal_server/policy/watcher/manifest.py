import asyncio
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

import aiohttp
from fastapi import status
from opal_common.logger import logger
from opal_common.utils import (
    build_aws_rest_auth_headers,
    get_authorization_header,
    throw_if_bad_status_code,
    tuple_to_dict,
)
from opal_server.config import (
    ApiPolicyBundleSources,
    PolicyBundleServerType,
    opal_server_config,
    validate_policy_bundle_source_mode,
)


def validate_resolved_source_paths(sources) -> None:
    clone_paths = []
    tmp_paths = []
    default_tmp_path = Path(opal_server_config.POLICY_BUNDLE_TMP_PATH)
    for source in sources:
        clone_path = source.clone_path or str(
            Path(opal_server_config.POLICY_REPO_CLONE_PATH)
            / f"{opal_server_config.POLICY_REPO_CLONE_FOLDER_PREFIX}_{source.source_id}"
        )
        tmp_path = source.tmp_path or str(
            default_tmp_path.with_name(
                f"{default_tmp_path.stem}-{source.source_id}{default_tmp_path.suffix}"
            )
        )
        clone_paths.append(Path(clone_path).expanduser().resolve())
        tmp_paths.append(Path(tmp_path).expanduser().resolve())

    if len(clone_paths) != len(set(clone_paths)):
        raise ValueError("API bundle sources must use distinct clone paths")
    if len(tmp_paths) != len(set(tmp_paths)):
        raise ValueError("API bundle sources must use distinct temporary paths")
    all_paths = clone_paths + tmp_paths
    if any(
        left == right or left in right.parents or right in left.parents
        for index, left in enumerate(all_paths)
        for right in all_paths[index + 1 :]
    ):
        raise ValueError(
            "API bundle source repositories and temporary paths must not overlap"
        )


class PolicyBundleManifestFetcher:
    def __init__(self):
        self.url = opal_server_config.POLICY_BUNDLE_MANIFEST_URL
        self.request_timeout = opal_server_config.POLICY_BUNDLE_MANIFEST_REQUEST_TIMEOUT
        self.server_type = opal_server_config.POLICY_BUNDLE_MANIFEST_SERVER_TYPE
        self.token = opal_server_config.POLICY_BUNDLE_MANIFEST_SERVER_TOKEN
        self.token_id = opal_server_config.POLICY_BUNDLE_MANIFEST_SERVER_TOKEN_ID
        self.region = opal_server_config.POLICY_BUNDLE_MANIFEST_SERVER_AWS_REGION
        self.etag: Optional[str] = None
        if self.request_timeout <= 0:
            raise ValueError("POLICY_BUNDLE_MANIFEST_REQUEST_TIMEOUT must be positive")
        if self.server_type == PolicyBundleServerType.AWS_S3 and not (
            self.token and self.token_id
        ):
            raise ValueError(
                "AWS-S3 manifest authentication requires both token and token ID"
            )

    def _auth_headers(self) -> dict:
        if self.server_type == PolicyBundleServerType.HTTP and self.token:
            return tuple_to_dict(get_authorization_header(self.token))
        if (
            self.server_type == PolicyBundleServerType.AWS_S3
            and self.token
            and self.token_id
        ):
            parsed_url = urlparse(self.url)
            return build_aws_rest_auth_headers(
                self.token_id,
                self.token,
                parsed_url.netloc,
                parsed_url.path or "/",
                self.region,
            )
        return {}

    async def fetch(self) -> Tuple[Optional[ApiPolicyBundleSources], Optional[str]]:
        headers = self._auth_headers()
        if self.etag:
            headers["If-None-Match"] = self.etag

        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        async with aiohttp.ClientSession(trust_env=True, timeout=timeout) as session:
            try:
                async with session.get(self.url, headers=headers) as response:
                    if response.status == status.HTTP_304_NOT_MODIFIED:
                        return None, self.etag
                    await throw_if_bad_status_code(
                        response, expected=[status.HTTP_200_OK], logger=logger
                    )
                    manifest = ApiPolicyBundleSources.model_validate(
                        await response.json()
                    )
                    validate_resolved_source_paths(manifest.sources)
                    self.etag = response.headers.get("ETag")
                    return manifest, self.etag
            except aiohttp.ClientError:
                logger.warning("Failed to fetch API bundle source manifest")
                raise


class PolicyBundleSourceRegistry:
    def __init__(self):
        validate_policy_bundle_source_mode(
            opal_server_config.POLICY_BUNDLE_SOURCES,
            opal_server_config.POLICY_BUNDLE_URL,
            opal_server_config.POLICY_BUNDLE_MANIFEST_URL,
        )
        self.fetcher = PolicyBundleManifestFetcher()
        self.refresh_interval = (
            opal_server_config.POLICY_BUNDLE_MANIFEST_REFRESH_INTERVAL
        )
        if self.refresh_interval <= 0:
            raise ValueError("POLICY_BUNDLE_MANIFEST_REFRESH_INTERVAL must be positive")
        self._sources: Optional[ApiPolicyBundleSources] = None
        self._last_error: Optional[Exception] = None
        self._last_refresh = 0.0
        self._lock = asyncio.Lock()

    async def get_sources(self, force: bool = False) -> ApiPolicyBundleSources:
        if not force and time.monotonic() - self._last_refresh < self.refresh_interval:
            if self._sources is not None:
                return self._sources
            raise RuntimeError(
                "Remote API bundle source manifest is not ready"
            ) from self._last_error

        async with self._lock:
            if (
                not force
                and time.monotonic() - self._last_refresh < self.refresh_interval
            ):
                if self._sources is not None:
                    return self._sources
                raise RuntimeError(
                    "Remote API bundle source manifest is not ready"
                ) from self._last_error
            try:
                sources, _ = await self.fetcher.fetch()
            except Exception as exc:
                self._last_refresh = time.monotonic()
                if self._sources is None:
                    self._last_error = exc
                    raise
                logger.warning(
                    "Manifest refresh failed; retaining last known-good sources "
                    "(error type: {error_type})",
                    error_type=type(exc).__name__,
                )
                return self._sources

            if sources is not None:
                self._sources = sources
            self._last_error = None
            self._last_refresh = time.monotonic()
            if self._sources is None:
                raise RuntimeError("Remote API bundle source manifest is empty")
            return self._sources


_source_registry: Optional[PolicyBundleSourceRegistry] = None


def get_policy_bundle_sources_registry() -> PolicyBundleSourceRegistry:
    global _source_registry
    if _source_registry is None:
        _source_registry = PolicyBundleSourceRegistry()
    return _source_registry


async def get_active_policy_bundle_sources() -> ApiPolicyBundleSources:
    if opal_server_config.POLICY_BUNDLE_MANIFEST_URL:
        return await get_policy_bundle_sources_registry().get_sources()
    return opal_server_config.POLICY_BUNDLE_SOURCES
