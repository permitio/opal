from opal_common.confi.confi import T
from typing import Any, Dict, Optional, List, Union
import uuid
from pydantic import BaseModel
from opal_common.schemas.policy import PolicyBundle
from contextlib import asynccontextmanager
from inspect import signature
from functools import partial
class PolicyStoreTranscationContextManager:

    def __init__(self, policy_store:"BasePolicyStoreClient", transaction_id=None) -> None:
        self._store = policy_store
        # make sure we have  a transaction id
        self._transaction_id = transaction_id or uuid.uuid4().hex

    def __getattribute__(self, name: str) -> Any:
        # internal members are prefixed with '-'
        if name.startswith("_"):
            # return internal members as is
            return super.__getattribute__(self,name)
        else:
            #proxy to wrapped store
            value = getattr(self._store)
            # methods that have a transcation id will get it automatically through this proxy
            if callable(value) and "transaction_id" in signature(value).parameters:
                return partial(value, transaction_id=self._transaction_id)
            # return properties / and regular methods as is
            else:
                return value

    async def __aenter__(self):
        await self._store.start_transaction(transaction_id=self._transaction_id)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._store.end_transcation(exc_type, exc, tb, transaction_id=self._transaction_id)


class BasePolicyStoreClient:
    """
    A pure-virtual interface for policy and policy-data store
    """

    async def start_transaction(self, transaction_id=None):
        """
        Start a series of operations with the policy store
        """
        pass

    async def end_transcation(self, exc=None, transaction_id:str=None):
        """
        Complete a series of operations with the policy store
        """        
        pass

    async def set_policy(self, policy_id: str, policy_code: str, transaction_id:Optional[str]=None):
        raise NotImplementedError()

    async def get_policy(self, policy_id: str, transaction_id:Optional[str]=None) -> Optional[str]:
        raise NotImplementedError()

    async def delete_policy(self, policy_id: str, transaction_id:Optional[str]=None):
        raise NotImplementedError()

    async def get_policy_module_ids(self, transaction_id:Optional[str]=None) -> List[str]:
        raise NotImplementedError()

    async def set_policies(self, bundle: PolicyBundle, transaction_id:Optional[str]=None):
        raise NotImplementedError()

    async def get_policy_version(self, transaction_id:Optional[str]=None) -> Optional[str]:
        raise NotImplementedError()

    async def set_policy_data(self, policy_data: Dict[str, Any], path: str = "", transaction_id:Optional[str]=None) -> Union[None, Any]:
        """
        Returns:
            Union[None, Any]: returning None indicates a failure to save to the policy-store
        """
        raise NotImplementedError()

    async def delete_policy_data(self, path: str = "", transaction_id:Optional[str]=None):
        raise NotImplementedError()

    async def get_data(self, path: str, transaction_id:Optional[str]=None) -> Dict:
        raise NotImplementedError()

    async def get_data_with_input(self, path: str, input: BaseModel, transaction_id:Optional[str]=None) -> Dict:
        raise NotImplementedError()