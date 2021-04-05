
from opal_client.policy_store.base_policy_store_client import BasePolicyStoreClient
from opal_client.config import opal_client_config, PolicyStoreTypes


class PolicyStoreClientFactoryException(Exception):
    pass


class InvalidPolicyStoreTypeException(Exception):
    pass


class PolicyStoreClientFactory:

    @staticmethod
    def create(store_type: PolicyStoreTypes = None, url: str = None) -> BasePolicyStoreClient:
        """Factory method - create a new policy store by type.

        Args:
            store_type (PolicyStoreTypes, optional): [description]. Defaults to opal_client_config.POLICY_STORE_TYPE.
            url ([type], optional): [description]. Defaults to opal_client_config.POLICY_STORE_URL.

        Raises:
            InvalidPolicyStoreTypeException: [description]

        Returns:
            BasePolicyStoreClient: the policy store client interface
        """
        # load defaults
        store_type = store_type or opal_client_config.POLICY_STORE_TYPE
        url = url or opal_client_config.POLICY_STORE_URL

        # OPA
        if PolicyStoreTypes.OPA == store_type:
            from opal_client.policy_store.opa_client import OpaClient
            return OpaClient(url)
        # MOCK
        elif PolicyStoreTypes.MOCK == store_type:
            from opal_client.policy_store.mock_policy_store_client import MockPolicyStoreClient
            return MockPolicyStoreClient()
        else:
            raise InvalidPolicyStoreTypeException(f"{store_type} is not a valid policy store type")


DEFAULT_POLICY_STORE_CREATOR = PolicyStoreClientFactory.create
