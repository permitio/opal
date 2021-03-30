from typing import Any, Dict, Optional, List
from pydantic import BaseModel
from opal_common.schemas.policy import PolicyBundle

class BasePolicyStoreClient:
    """
    A pure-virtual interface for policy and policy-data store
    """
    async def set_policy(self, policy_id: str, policy_code: str):
        raise NotImplementedError()

    async def get_policy(self, policy_id: str) -> Optional[str]:
        raise NotImplementedError()

    async def delete_policy(self, policy_id: str):
        raise NotImplementedError()

    async def get_policy_module_ids(self) -> List[str]:
        raise NotImplementedError()

    async def set_policies(self, bundle: PolicyBundle):
        raise NotImplementedError()

    async def get_policy_version(self) -> Optional[str]:
        raise NotImplementedError()

    async def set_policy_data(self, policy_data: Dict[str, Any], path: str = ""):
        raise NotImplementedError()

    async def delete_policy_data(self, path: str = ""):
        raise NotImplementedError()

    async def get_data(self, path: str) -> Dict:
        raise NotImplementedError()

    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        raise NotImplementedError()