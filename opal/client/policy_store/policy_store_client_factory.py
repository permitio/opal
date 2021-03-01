
from opal.client.config import POLICY_STORE_TYPE, PolicyStoreTypes, POLICY_STORE_URL


class PolicyStoreClientFactoryException(Exception):
    pass

class InvalidPolicyStoreTypeException(Exception):
    pass



class PolicyStoreClientFactory:

    @classmethod
    def create(type=POLICY_STORE_TYPE, url=POLICY_STORE_URL):
        # OPA
        if PolicyStoreTypes.OPA == type:
            from opal.client.policy_store.opa_client import OpaClient
            return OpaClient(url)
        # MOCK
        elif PolicyStoreTypes.MOCK == type:
            from opal.client.policy_store.mock_policy_store_client import MockPolicyStoreClient
            return MockPolicyStoreClient()
        else:
            raise InvalidPolicyStoreTypeException(f"{type} is not a valid policy store type")


policy_store = PolicyStoreClientFactory.create()