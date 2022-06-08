import asyncio
from typing import Any, Dict, List, Optional

from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.store import StoreTransaction
from pydantic import BaseModel

from .base_policy_store_client import BasePolicyStoreClient, JsonableValue


class MockPolicyStoreClient(BasePolicyStoreClient):
    """A naive mock policy and policy-data store for tests."""

    def __init__(self) -> None:
        super().__init__()
        self._has_data_event: asyncio.Event() = None
        self._data = {}

    @property
    def has_data_event(self):
        if self._has_data_event is None:
            self._has_data_event = asyncio.Event()
        return self._has_data_event

    async def set_policy(
        self, policy_id: str, policy_code: str, transaction_id: Optional[str] = None
    ):
        pass

    async def get_policy(self, policy_id: str) -> Optional[str]:
        pass

    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        pass

    async def get_policy_module_ids(self) -> List[str]:
        pass

    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        pass

    async def get_policy_version(self) -> Optional[str]:
        return None

    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        self._data[path] = policy_data
        self.has_data_event.set()

    async def get_data(self, path: str = None) -> Dict:
        if path is None or path == "":
            return self._data
        else:
            return self._data[path]

    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        return {}

    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        if not path:
            self._data = {}
        else:
            del self._data[path]

    async def patch_data(
        self,
        path: str,
        patch_document: Dict[str, Any],
        transaction_id: Optional[str] = None,
    ):
        pass

    async def wait_for_data(self):
        """Wait until the store has data set in it."""
        await self.has_data_event.wait()

    async def init_healthcheck_policy(
        self, policy_id: str, policy_code: str, data_updater_enabled: bool = True
    ):
        pass

    async def persist_transaction(self, transaction: StoreTransaction):
        pass
