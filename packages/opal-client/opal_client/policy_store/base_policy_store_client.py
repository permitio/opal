import json
import uuid
from datetime import datetime
from functools import partial
from inspect import signature
from typing import Any, Dict, List, Optional, Union

from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_common.schemas.data import JsonableValue
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.store import RemoteStatus, StoreTransaction
from pydantic import BaseModel


class AbstractPolicyStore:
    """holds only the interface of a policy store."""

    async def set_policy(
        self, policy_id: str, policy_code: str, transaction_id: Optional[str] = None
    ):
        raise NotImplementedError()

    async def get_policy(self, policy_id: str) -> Optional[str]:
        raise NotImplementedError()

    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        raise NotImplementedError()

    async def get_policy_module_ids(self) -> List[str]:
        raise NotImplementedError()

    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        raise NotImplementedError()

    async def get_policy_version(self) -> Optional[str]:
        raise NotImplementedError()

    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        raise NotImplementedError()

    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        raise NotImplementedError()

    async def patch_data(
        self,
        path: str,
        patch_document: Dict[str, Any],
        transaction_id: Optional[str] = None,
    ):
        raise NotImplementedError()

    async def get_data(self, path: str) -> Dict:
        raise NotImplementedError()

    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        raise NotImplementedError()

    async def init_healthcheck_policy(
        self, policy_id: str, policy_code: str, data_updater_enabled: bool = True
    ):
        raise NotImplementedError()

    async def persist_transaction(self, transaction: StoreTransaction):
        raise NotImplementedError()


class PolicyStoreTransactionContextManager(AbstractPolicyStore):
    def __init__(
        self,
        policy_store: "BasePolicyStoreClient",
        transaction_id=None,
        transaction_type=None,
        creation_time=None,
    ) -> None:
        self._store = policy_store
        # make sure we have  a transaction id
        self._transaction_id = transaction_id or uuid.uuid4().hex
        self._actions = []
        self._remotes_status: List[RemoteStatus] = []
        self._transaction_type = transaction_type
        self._creation_time = datetime.utcnow().isoformat()

    def __getattribute__(self, name: str) -> Any:
        # internal members are prefixed with '-'
        if name.startswith("_"):
            # return internal members as is
            return super().__getattribute__(name)
        else:
            # proxy to wrapped store
            store_attr = getattr(self._store, name)
            # methods that have a transcation id will get it automatically through this proxy
            if callable(store_attr) and (
                "transaction_id" in signature(store_attr).parameters
                or hasattr(store_attr, "affects_transaction")
            ):
                # record the call as an action in the transaction
                self._actions.append(name)
                return partial(store_attr, transaction_id=self._transaction_id)
            # return properties / and regular methods as is
            else:
                return store_attr

    def _update_remote_status(self, url: str, status: bool, error: str):
        self._remotes_status.append(
            {"remote_url": url, "succeed": status, "error": error}
        )

    async def __aenter__(self):
        await self._store.start_transaction(transaction_id=self._transaction_id)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._store.end_transcation(
            exc_type,
            exc,
            tb,
            transaction_id=self._transaction_id,
            actions=self._actions,
            transaction_type=self._transaction_type,
            remotes_status=self._remotes_status,
            creation_time=self._creation_time,
        )


class BasePolicyStoreClient(AbstractPolicyStore):
    """An interface for policy and policy-data store."""

    def transaction_context(
        self, transaction_id: str, transaction_type: str
    ) -> PolicyStoreTransactionContextManager:
        """
        Args:
            transaction_id : the id of the transaction

        Returns:
            PolicyStoreTranscationContextManager: a context manager for a transaction to be used in a async with statement
        """
        return PolicyStoreTransactionContextManager(
            self, transaction_id=transaction_id, transaction_type=transaction_type
        )

    async def start_transaction(self, transaction_id: str = None):
        """PolicyStoreTranscationContextManager calls here on __aenter__ Start
        a series of operations with the policy store."""
        pass

    async def end_transcation(
        self,
        exc_type=None,
        exc=None,
        tb=None,
        transaction_id: str = None,
        actions: List[str] = None,
        transaction_type: str = None,
        remotes_status: Optional[List[RemoteStatus]] = None,
        creation_time=None,
    ):
        """PolicyStoreTranscationContextManager calls here on __aexit__
        Complete a series of operations with the policy store.

        Args:
            exc_type: The exception type (if raised). Defaults to None.
            exc: The exception type (if raised). Defaults to None.
            tb: The traceback (if raised). Defaults to None.
            transaction_id (str, optional): The transaction id. Defaults to None.
            actions (List[str], optional): All the methods called in the transaction. Defaults to None.
        """
        exception_fetching_transaction = []
        if remotes_status:
            exception_fetching_transaction = [
                remote for remote in remotes_status if not remote["succeed"]
            ]
        elif transaction_id is None or not actions:
            return  # skip, nothing to do if we have no data to log

        end_time = datetime.utcnow().isoformat()
        if exc is not None or exception_fetching_transaction:
            try:
                if exc is not None:
                    error_message = repr(exc)
                elif exception_fetching_transaction:
                    network_errors = [
                        remote.get("error", None)
                        for remote in exception_fetching_transaction
                    ]
                    network_errors = [
                        str(err) for err in network_errors if err is not None
                    ]
                    error_message = ";".join(network_errors) if network_errors else None
                else:
                    error_message = None
            except:  # maybe repr throws here
                error_message = None

            transaction = StoreTransaction(
                id=transaction_id,
                actions=actions,
                success=False,
                error=error_message or "",
                creation_time=creation_time,
                end_time=end_time,
                transaction_type=transaction_type,
                remotes_status=remotes_status,
            )

            logger.error(
                "OPA transaction failed, transaction id={id}, actions={actions}, error={err}",
                id=transaction_id,
                actions=repr(actions),
                err=error_message,
            )
        else:
            transaction = StoreTransaction(
                id=transaction_id,
                actions=actions,
                success=True,
                creation_time=creation_time,
                end_time=end_time,
                transaction_type=transaction_type,
                remotes_status=remotes_status,
            )

        if not opal_client_config.OPA_HEALTH_CHECK_POLICY_ENABLED:
            return  # skip persisting the transaction, healthcheck policy is disabled

        try:
            await self.persist_transaction(transaction)
        except Exception as e:
            # The writes to transaction log in OPA cache are not done a protected
            # transaction context. If they fail, we do nothing special.
            transaction_data = json.dumps(
                transaction, indent=4, sort_keys=True, default=str
            )
            logger.error(
                "Cannot write to OPAL transaction log, transaction id={id}, error={err} with data={data}",
                id=transaction.id,
                err=repr(e),
                data=transaction_data,
            )
