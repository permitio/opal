from typing import Dict, Optional

from opal_client.config import opal_client_config
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.policy_store.schemas import PolicyStoreAuth, PolicyStoreTypes


class PolicyStoreClientFactoryException(Exception):
    pass


class InvalidPolicyStoreTypeException(Exception):
    pass


class PolicyStoreClientFactory:
    CACHE: Dict[str, BasePolicyStoreClient] = {}

    @classmethod
    def get(
        cls,
        store_type: PolicyStoreTypes = None,
        url: str = None,
        save_to_cache=True,
        token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        oauth_server: Optional[str] = None,
    ) -> BasePolicyStoreClient:
        """Same as self.create() but with caching.

        Args:
            store_type (PolicyStoreTypes, optional): The type of policy-store to use. Defaults to opal_client_config.POLICY_STORE_TYPE.
            url (str, optional): the URL of the policy store. Defaults to opal_client_config.POLICY_STORE_URL.
            save_to_cache (bool, optional): Should the created value be saved to cache (To be obtained via the get method).

        Raises:
            InvalidPolicyStoreTypeException: Raised when the factory doesn't have a store-client matching the given type

        Returns:
            BasePolicyStoreClient: the policy store client interface
        """
        # get from cache if available - else create anew
        key = cls.get_cache_key(store_type, url)
        value = cls.CACHE.get(key, None)
        if value is None:
            return cls.create(
                store_type=store_type,
                url=url,
                save_to_cache=save_to_cache,
                token=token,
                auth_type=auth_type,
                oauth_client_id=oauth_client_id,
                oauth_client_secret=oauth_client_secret,
                oauth_server=oauth_server,
            )
        else:
            return value

    @classmethod
    def create(
        cls,
        store_type: PolicyStoreTypes = None,
        url: str = None,
        save_to_cache=True,
        token: Optional[str] = None,
        auth_type: PolicyStoreAuth = None,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        oauth_server: Optional[str] = None,
        data_updater_enabled: Optional[bool] = None,
        policy_updater_enabled: Optional[bool] = None,
        offline_mode_enabled: bool = False,
        tls_client_cert: Optional[str] = None,
        tls_client_key: Optional[str] = None,
        tls_ca: Optional[str] = None,
    ) -> BasePolicyStoreClient:
        """
        Factory method - create a new policy store by type.

        Args:
            store_type (PolicyStoreTypes, optional): The type of policy-store to use. Defaults to opal_client_config.POLICY_STORE_TYPE.
            url (str, optional): the URL of the policy store. Defaults to opal_client_config.POLICY_STORE_URL.
            save_to_cache (bool, optional): Should the created value be saved to cache (To be obtained via the get method).

        Raises:
            InvalidPolicyStoreTypeException: Raised when the factory doesn't have a store-client matching the given type

        Returns:
            BasePolicyStoreClient: the policy store client interface
        """
        # load defaults
        store_type = store_type or opal_client_config.POLICY_STORE_TYPE
        url = url or opal_client_config.POLICY_STORE_URL
        store_token = token or opal_client_config.POLICY_STORE_AUTH_TOKEN

        auth_type = auth_type or opal_client_config.POLICY_STORE_AUTH_TYPE
        oauth_client_id = (
            oauth_client_id or opal_client_config.POLICY_STORE_AUTH_OAUTH_CLIENT_ID
        )
        oauth_client_secret = (
            oauth_client_secret
            or opal_client_config.POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET
        )
        oauth_server = oauth_server or opal_client_config.POLICY_STORE_AUTH_OAUTH_SERVER
        data_updater_enabled = (
            data_updater_enabled
            if data_updater_enabled is not None
            else opal_client_config.DATA_UPDATER_ENABLED
        )
        policy_updater_enabled = (
            policy_updater_enabled
            if policy_updater_enabled is not None
            else opal_client_config.POLICY_UPDATER_ENABLED
        )

        res: Optional[BasePolicyStoreClient] = None
        tls_client_cert = (
            tls_client_cert or opal_client_config.POLICY_STORE_TLS_CLIENT_CERT
        )

        tls_client_key = (
            tls_client_key or opal_client_config.POLICY_STORE_TLS_CLIENT_KEY
        )

        tls_ca = tls_ca or opal_client_config.POLICY_STORE_TLS_CA

        # OPA
        if PolicyStoreTypes.OPA == store_type:
            from opal_client.policy_store.opa_client import OpaClient

            res = OpaClient(
                url,
                opa_auth_token=store_token,
                auth_type=auth_type,
                oauth_client_id=oauth_client_id,
                oauth_client_secret=oauth_client_secret,
                oauth_server=oauth_server,
                data_updater_enabled=data_updater_enabled,
                policy_updater_enabled=policy_updater_enabled,
                cache_policy_data=offline_mode_enabled,
                tls_client_cert=tls_client_cert,
                tls_client_key=tls_client_key,
                tls_ca=tls_ca,
            )
        elif PolicyStoreTypes.CEDAR == store_type:
            from opal_client.policy_store.cedar_client import CedarClient

            res = CedarClient(
                url,
                cedar_auth_token=store_token,
                auth_type=auth_type,
            )
        # MOCK
        elif PolicyStoreTypes.MOCK == store_type:
            from opal_client.policy_store.mock_policy_store_client import (
                MockPolicyStoreClient,
            )

            res = MockPolicyStoreClient()

        if res is None:
            raise InvalidPolicyStoreTypeException(
                f"{store_type} is not a valid policy store type"
            )

        # save to cache
        if save_to_cache:
            cls.CACHE[cls.get_cache_key(store_type, url)] = res
        # return the result
        return res

    @staticmethod
    def get_cache_key(store_type, url):
        return f"{store_type.value}|{url}"


DEFAULT_POLICY_STORE_GETTER = PolicyStoreClientFactory.get
