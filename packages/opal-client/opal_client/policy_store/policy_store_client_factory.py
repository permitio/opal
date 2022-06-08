from typing import Dict, Optional

from opal_client.config import opal_client_config
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.policy_store.schemas import PolicyStoreTypes


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
    ) -> BasePolicyStoreClient:
        """Same as self.create() but with caching.

        Args:
            store_type (PolicyStoreTypes, optional): The type of policy-store to use. Defaults to opal_client_config.POLICY_STORE_TYPE.
            url (str, optional): the URL of the policy store. Defaults to opal_client_config.POLICY_STORE_URL.
            save_to_cache (bool, optional): Should the created value be saved to cache (To be obtained via the get method).

        Raises:
            InvalidPolicyStoreTypeException: Raised when the factory doesn't have a store-client macthing the given type

        Returns:
            BasePolicyStoreClient: the policy store client interface
        """
        # get from cache if available - else create anew
        key = cls.get_cache_key(store_type, url)
        value = cls.CACHE.get(key, None)
        if value is None:
            return cls.create(store_type, url, token)
        else:
            return value

    @classmethod
    def create(
        cls,
        store_type: PolicyStoreTypes = None,
        url: str = None,
        save_to_cache=True,
        token: Optional[str] = None,
    ) -> BasePolicyStoreClient:
        """
        Factory method - create a new policy store by type.

        Args:
            store_type (PolicyStoreTypes, optional): The type of policy-store to use. Defaults to opal_client_config.POLICY_STORE_TYPE.
            url (str, optional): the URL of the policy store. Defaults to opal_client_config.POLICY_STORE_URL.
            save_to_cache (bool, optional): Should the created value be saved to cache (To be obtained via the get method).

        Raises:
            InvalidPolicyStoreTypeException: Raised when the factory doesn't have a store-client macthing the given type

        Returns:
            BasePolicyStoreClient: the policy store client interface
        """
        # load defaults
        store_type = store_type or opal_client_config.POLICY_STORE_TYPE
        url = url or opal_client_config.POLICY_STORE_URL
        store_token = token or opal_client_config.POLICY_STORE_AUTH_TOKEN

        # OPA
        if PolicyStoreTypes.OPA == store_type:
            from opal_client.policy_store.opa_client import OpaClient

            res = OpaClient(url, opa_auth_token=store_token)
        # MOCK
        elif PolicyStoreTypes.MOCK == store_type:
            from opal_client.policy_store.mock_policy_store_client import (
                MockPolicyStoreClient,
            )

            res = MockPolicyStoreClient()
        else:
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
