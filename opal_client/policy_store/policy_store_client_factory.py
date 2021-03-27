
from opal_client.config import POLICY_STORE_TYPE, PolicyStoreTypes, POLICY_STORE_URL


class PolicyStoreClientFactoryException(Exception):
    pass

class InvalidPolicyStoreTypeException(Exception):
    pass



class PolicyStoreClientFactory:

    @staticmethod
    def create(store_type=POLICY_STORE_TYPE, url=POLICY_STORE_URL):
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


DEFAULT_POLICY_STORE = PolicyStoreClientFactory.create()