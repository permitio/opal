from typing import Any, Dict, Optional

from opal_client.config import opal_client_config
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreTypes


class PolicyStoreClientFactoryException(Exception):
    pass


class InvalidPolicyStoreTypeException(Exception):
    pass


def _coalesce_option(options: Dict[str, Any], spec: tuple[str, Any]) -> Any:
    key, fallback = spec
    val = options.get(key)
    return val if val is not None else fallback


def _resolve_factory_options(
    store_type: Optional[PolicyStoreTypes],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    defaults = (
        ("url", opal_client_config.POLICY_STORE_URL),
        ("save_to_cache", True),
        ("token", opal_client_config.POLICY_STORE_AUTH_TOKEN),
        ("auth_type", opal_client_config.POLICY_STORE_AUTH_TYPE),
        ("oauth_client_id", opal_client_config.POLICY_STORE_AUTH_OAUTH_CLIENT_ID),
        (
            "oauth_client_secret",
            opal_client_config.POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET,
        ),
        ("oauth_server", opal_client_config.POLICY_STORE_AUTH_OAUTH_SERVER),
        ("data_updater_enabled", opal_client_config.DATA_UPDATER_ENABLED),
        ("policy_updater_enabled", opal_client_config.POLICY_UPDATER_ENABLED),
        ("offline_mode_enabled", False),
        ("tls_client_cert", opal_client_config.POLICY_STORE_TLS_CLIENT_CERT),
        ("tls_client_key", opal_client_config.POLICY_STORE_TLS_CLIENT_KEY),
        ("tls_ca", opal_client_config.POLICY_STORE_TLS_CA),
    )
    resolved: Dict[str, Any] = {
        "store_type": store_type or opal_client_config.POLICY_STORE_TYPE
    }
    for key, fallback in defaults:
        resolved[key] = _coalesce_option(options, (key, fallback))
    resolved["store_token"] = resolved["token"]
    return resolved


def _build_opa_client(resolved: Dict[str, Any]) -> BasePolicyStoreClient:
    from opal_client.policy_store.opa_client import OpaClient

    return OpaClient(
        resolved["url"],
        opa_auth_token=resolved["store_token"],
        auth_type=resolved["auth_type"],
        oauth_client_id=resolved["oauth_client_id"],
        oauth_client_secret=resolved["oauth_client_secret"],
        oauth_server=resolved["oauth_server"],
        data_updater_enabled=resolved["data_updater_enabled"],
        policy_updater_enabled=resolved["policy_updater_enabled"],
        cache_policy_data=resolved["offline_mode_enabled"],
        tls_client_cert=resolved["tls_client_cert"],
        tls_client_key=resolved["tls_client_key"],
        tls_ca=resolved["tls_ca"],
    )


def _build_cedar_client(resolved: Dict[str, Any]) -> BasePolicyStoreClient:
    from opal_client.policy_store.cedar_client import CedarClient

    return CedarClient(
        resolved["url"],
        cedar_auth_token=resolved["store_token"],
        auth_type=resolved["auth_type"],
    )


def _build_openfga_client(resolved: Dict[str, Any]) -> BasePolicyStoreClient:
    from opal_client.policy_store.openfga_client import OpenFGAClient

    return OpenFGAClient(
        resolved["url"],
        openfga_auth_token=resolved["store_token"],
        auth_type=resolved["auth_type"],
        oauth_client_id=resolved["oauth_client_id"],
        oauth_client_secret=resolved["oauth_client_secret"],
        oauth_server=resolved["oauth_server"],
        store_id=opal_client_config.OPENFGA_STORE_ID,
        store_name=opal_client_config.OPENFGA_STORE_NAME,
        authorization_model_id=opal_client_config.OPENFGA_AUTHORIZATION_MODEL_ID,
    )


def _instantiate_policy_store(resolved: Dict[str, Any]) -> BasePolicyStoreClient:
    store_type = resolved["store_type"]
    if store_type == PolicyStoreTypes.OPA:
        return _build_opa_client(resolved)
    if store_type == PolicyStoreTypes.CEDAR:
        return _build_cedar_client(resolved)
    if store_type == PolicyStoreTypes.OPENFGA:
        return _build_openfga_client(resolved)
    if store_type == PolicyStoreTypes.MOCK:
        from opal_client.policy_store.mock_policy_store_client import (
            MockPolicyStoreClient,
        )

        return MockPolicyStoreClient()
    raise InvalidPolicyStoreTypeException(
        f"{store_type} is not a valid policy store type"
    )


class PolicyStoreClientFactory:
    CACHE: Dict[str, BasePolicyStoreClient] = {}

    @classmethod
    def get(
        cls,
        store_type: PolicyStoreTypes = None,
        url: str = None,
        **kwargs: Any,
    ) -> BasePolicyStoreClient:
        key = cls.get_cache_key(store_type, url)
        value = cls.CACHE.get(key)
        if value is not None:
            return value
        kwargs.setdefault("auth_type", PolicyStoreAuth.NONE)
        return cls.create(store_type=store_type, url=url, **kwargs)

    @classmethod
    def create(
        cls,
        store_type: PolicyStoreTypes = None,
        url: str = None,
        **kwargs: Any,
    ) -> BasePolicyStoreClient:
        options = dict(kwargs)
        options["url"] = url
        resolved = _resolve_factory_options(store_type, options)
        client = _instantiate_policy_store(resolved)
        if resolved["save_to_cache"]:
            cache_key = cls.get_cache_key(resolved["store_type"], resolved["url"])
            cls.CACHE[cache_key] = client
        return client

    @staticmethod
    def get_cache_key(store_type, url):
        return f"{store_type.value}|{url}"


DEFAULT_POLICY_STORE_GETTER = PolicyStoreClientFactory.get
