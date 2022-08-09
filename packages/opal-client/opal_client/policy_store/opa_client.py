import asyncio
import functools
import json
from typing import Any, Dict, List, Optional, Set

import aiohttp
from fastapi import Response, status
from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_client.policy_store.base_policy_store_client import (
    BasePolicyStoreClient,
    JsonableValue,
)
from opal_client.utils import proxy_response
from opal_common.git.bundle_utils import BundleUtils
from opal_common.opa.parsing import get_rego_package
from opal_common.schemas.policy import DataModule, PolicyBundle
from opal_common.schemas.store import JSONPatchAction, StoreTransaction, TransactionType
from pydantic import BaseModel
from tenacity import retry

JSONPatchDocument = List[JSONPatchAction]


RETRY_CONFIG = opal_client_config.POLICY_STORE_CONN_RETRY.toTenacityConfig()


def fail_silently(fallback=None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except aiohttp.ClientError as e:
                return fallback

        return wrapper

    return decorator


def affects_transaction(func):
    """mark a method as write (affecting state of transaction) for transaction
    log."""
    setattr(func, "affects_transaction", True)
    return func


async def proxy_response_unless_invalid(
    raw_response: aiohttp.ClientResponse, accepted_status_codes: List[int]
) -> Response:
    """throws value error if the http response recieved has an unexpected
    status code."""
    response = await proxy_response(raw_response)
    if response.status_code not in accepted_status_codes:
        try:
            error = await raw_response.json()
        except json.JSONDecodeError:
            error = ""
        raise ValueError(
            "OPA Client: unexpected status code: {}, error: {}".format(
                response.status_code, error
            )
        )
    return response


class OpaTransactionLogState:
    """holds a mutatable state of the transaction log.

    can persist to OPA as hardcoded policy
    """

    POLICY_ACTIONS = ["set_policies", "set_policy", "delete_policy"]
    DATA_ACTIONS = ["set_policy_data", "delete_policy_data"]

    def __init__(
        self,
        policy_store: BasePolicyStoreClient,
        policy_id: str,
        policy_template: str,
        data_updater_enabled: bool = True,
    ):
        self._store = policy_store
        self._policy_id = policy_id
        self._policy_template = policy_template
        self._data_updater_disabled = not data_updater_enabled
        self._num_successful_policy_transactions = 0
        self._num_failed_policy_transactions = 0
        self._num_successful_data_transactions = 0
        self._num_failed_data_transactions = 0
        self._last_policy_transaction: Optional[StoreTransaction] = None
        self._last_failed_policy_transaction: Optional[StoreTransaction] = None
        self._last_data_transaction: Optional[StoreTransaction] = None
        self._last_failed_data_transaction: Optional[StoreTransaction] = None

    @property
    def ready(self) -> bool:
        is_ready: bool = self._num_successful_policy_transactions > 0 and (
            self._data_updater_disabled or self._num_successful_data_transactions > 0
        )
        return json.dumps(is_ready)

    @property
    def healthy(self) -> bool:
        policy_updater_is_healthy: bool = (
            self._last_policy_transaction is not None
            and self._last_policy_transaction.success
        )
        data_updater_is_healthy: bool = (
            self._last_data_transaction is not None
            and self._last_data_transaction.success
        )
        is_healthy: bool = policy_updater_is_healthy and (
            self._data_updater_disabled or data_updater_is_healthy
        )
        return json.dumps(is_healthy)

    @property
    def last_policy_transaction(self):
        if self._last_policy_transaction is None:
            return json.dumps({})
        return json.dumps(self._last_policy_transaction.dict())

    @property
    def last_data_transaction(self):
        if self._last_data_transaction is None:
            return json.dumps({})
        return json.dumps(self._last_data_transaction.dict())

    @property
    def last_failed_policy_transaction(self):
        if self._last_failed_policy_transaction is None:
            return json.dumps({})
        return json.dumps(self._last_failed_policy_transaction.dict())

    @property
    def last_failed_data_transaction(self):
        if self._last_failed_data_transaction is None:
            return json.dumps({})
        return json.dumps(self._last_failed_data_transaction.dict())

    @property
    def transaction_policy_statistics(self):
        return json.dumps(
            {
                "successful": self._num_successful_policy_transactions,
                "failed": self._num_failed_policy_transactions,
            }
        )

    @property
    def transaction_data_statistics(self):
        return json.dumps(
            {
                "successful": self._num_successful_data_transactions,
                "failed": self._num_failed_data_transactions,
            }
        )

    async def persist(self):
        """renders the policy template with the current state, and writes it to
        OPA."""
        logger.info(
            "persisting health check policy: ready={ready}, healthy={healthy}",
            ready=self.ready,
            healthy=self.healthy,
        )
        logger.info(
            "Policy and data statistics: policy: (successful {success_policy}, failed {failed_policy});\tdata: (successful {success_data}, failed {failed_data})",
            success_policy=self._num_successful_policy_transactions,
            failed_policy=self._num_failed_policy_transactions,
            success_data=self._num_successful_data_transactions,
            failed_data=self._num_failed_data_transactions,
        )
        policy_code = self._policy_template.format(
            ready=self.ready,
            healthy=self.healthy,
            last_policy_transaction=self.last_policy_transaction,
            last_failed_policy_transaction=self.last_failed_policy_transaction,
            last_data_transaction=self.last_data_transaction,
            last_failed_data_transaction=self.last_failed_data_transaction,
            transaction_data_statistics=self.transaction_data_statistics,
            transaction_policy_statistics=self.transaction_policy_statistics,
        )
        return await self._store.set_policy(
            policy_id=self._policy_id, policy_code=policy_code
        )

    def _is_policy_transaction(self, transaction: StoreTransaction):
        return transaction.transaction_type == TransactionType.policy

    def _is_data_transaction(self, transaction: StoreTransaction):
        return transaction.transaction_type == TransactionType.data

    def process_transaction(self, transaction: StoreTransaction):
        """mutates the state into a new state that can be then persisted as
        hardcoded policy."""
        logger.info(
            "processing store transaction: {transaction}",
            transaction=transaction.dict(),
        )
        if self._is_policy_transaction(transaction):

            if transaction.success:
                self._last_policy_transaction = transaction
                self._num_successful_policy_transactions += 1
            else:
                self._last_failed_policy_transaction = transaction
                self._num_failed_policy_transactions += 1

        elif self._is_data_transaction(transaction):

            if transaction.success:
                self._last_data_transaction = transaction
                self._num_successful_data_transactions += 1
            else:
                self._last_failed_data_transaction = transaction
                self._num_failed_data_transactions += 1


class OpaClient(BasePolicyStoreClient):
    """communicates with OPA via its REST API."""

    POLICY_NAME = "rbac"

    def __init__(self, opa_server_url=None, opa_auth_token: Optional[str] = None):
        base_url = opa_server_url or opal_client_config.POLICY_STORE_URL
        self._opa_url = f"{base_url}/v1"
        self._cached_policies: Dict[str, str] = {}
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()
        self._token = opa_auth_token
        self._headers = {}
        if opa_auth_token is not None:
            self._headers.update({"Authorization": f"Bearer {opa_auth_token}"})

        # as long as this is null, transaction log is disabled
        self._transaction_state: Optional[OpaTransactionLogState] = None

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy(
        self, policy_id: str, policy_code: str, transaction_id: Optional[str] = None
    ):
        self._cached_policies[policy_id] = policy_code
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    f"{self._opa_url}/policies/{policy_id}",
                    data=policy_code,
                    headers={"content-type": "text/plain", **self._headers},
                ) as opa_response:
                    return await proxy_response_unless_invalid(
                        opa_response, accepted_status_codes=[status.HTTP_200_OK]
                    )
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self._opa_url}/policies/{policy_id}", headers=self._headers
                ) as opa_response:
                    result = await opa_response.json()
                    return result.get("result", {}).get("raw", None)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.delete(
                    f"{self._opa_url}/policies/{policy_id}", headers=self._headers
                ) as opa_response:
                    return await proxy_response_unless_invalid(
                        opa_response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_404_NOT_FOUND,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy_module_ids(self) -> List[str]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self._opa_url}/policies", headers=self._headers
                ) as opa_response:
                    result = await opa_response.json()
                    return OpaClient._extract_module_ids_from_policies_json(result)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @staticmethod
    def _extract_module_ids_from_policies_json(result: Dict[str, Any]) -> List[str]:
        """return all module ids in OPA cache who are not:

        - skipped module ids (i.e: our health check policy)
        - all modules with package name starting with "system" (special OPA policies)
        """
        modules: List[Dict[str, Any]] = result.get("result", [])
        builtin_modules = [opal_client_config.OPA_HEALTH_CHECK_POLICY_PATH]

        module_ids = []
        for module in modules:
            module_id = module.get("id", None)
            package_name = get_rego_package(module.get("raw", ""))

            if module_id is None:
                continue

            if package_name is not None and package_name.startswith("system."):
                continue

            if module_id in builtin_modules:
                continue

            module_ids.append(module_id)

        return module_ids

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        if bundle.old_hash is None:
            return await self._set_policies_from_complete_bundle(bundle)
        else:
            return await self._set_policies_from_delta_bundle(bundle)

    async def _set_policies_from_complete_bundle(self, bundle: PolicyBundle):
        module_ids_in_store: Set[str] = set(await self.get_policy_module_ids())
        module_ids_in_bundle: Set[str] = {
            module.path for module in bundle.policy_modules
        }
        module_ids_to_delete: Set[str] = module_ids_in_store.difference(
            module_ids_in_bundle
        )

        async with self._lock:
            # save bundled policy *static* data into store
            for module in BundleUtils.sorted_data_modules_to_load(bundle):
                await self._set_policy_data_from_bundle_data_module(
                    module, hash=bundle.hash
                )

            # save bundled policies into store
            for module in BundleUtils.sorted_policy_modules_to_load(bundle):
                await self.set_policy(policy_id=module.path, policy_code=module.rego)

            # remove policies from the store that are not in the bundle
            # (because this bundle is "complete", i.e: contains all policy modules for a given hash)
            for module_id in module_ids_to_delete:
                await self.delete_policy(policy_id=module_id)

            # save policy version (hash) into store
            self._policy_version = bundle.hash

    async def _set_policies_from_delta_bundle(self, bundle: PolicyBundle):
        async with self._lock:
            # save bundled policy *static* data into store
            for module in BundleUtils.sorted_data_modules_to_load(bundle):
                await self._set_policy_data_from_bundle_data_module(
                    module, hash=bundle.hash
                )

            # save bundled policies into store
            for module in BundleUtils.sorted_policy_modules_to_load(bundle):
                await self.set_policy(policy_id=module.path, policy_code=module.rego)

            # remove deleted policies (or static policy data) from store
            if bundle.deleted_files is not None:
                for module_id in BundleUtils.sorted_policy_modules_to_delete(bundle):
                    await self.delete_policy(policy_id=module_id)

                for module_id in BundleUtils.sorted_data_modules_to_delete(bundle):
                    await self.delete_policy_data(
                        path=self._safe_data_module_path(str(module_id))
                    )

            # save policy version (hash) into store
            self._policy_version = bundle.hash

    @classmethod
    def _safe_data_module_path(cls, path: str):
        if not path or path == ".":
            return ""

        if not path.startswith("/"):
            return f"/{path}"

        return path

    async def _set_policy_data_from_bundle_data_module(
        self, module: DataModule, hash: Optional[str] = None
    ):
        module_path = self._safe_data_module_path(module.path)
        try:
            module_data = json.loads(module.data)
            return await self.set_policy_data(
                policy_data=module_data,
                path=module_path,
            )
        except aiohttp.ClientError as e:
            logger.warning("Opa connection error: {err}", err=repr(e))
            raise
        except json.JSONDecodeError as e:
            logger.warning(
                "bundle contains non-json data module: {module_path}",
                err=repr(e),
                module_path=module_path,
                bundle_hash=hash,
            )

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        path = self._safe_data_module_path(path)

        # in OPA, the root document must be an object, so we must wrap list values
        if not path and isinstance(policy_data, list):
            logger.warning(
                "OPAL client was instructed to put a list on OPA's root document. In OPA the root document must be an object so the original value was wrapped."
            )
            policy_data = {"items": policy_data}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    f"{self._opa_url}/data{path}",
                    data=json.dumps(policy_data, default=str),
                    headers=self._headers,
                ) as opa_response:
                    return await proxy_response_unless_invalid(
                        opa_response,
                        accepted_status_codes=[
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_304_NOT_MODIFIED,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        path = self._safe_data_module_path(path)
        if not path:
            return await self.set_policy_data({})

        async with aiohttp.ClientSession() as session:
            try:
                async with session.delete(
                    f"{self._opa_url}/data{path}", headers=self._headers
                ) as opa_response:
                    return await proxy_response_unless_invalid(
                        opa_response,
                        accepted_status_codes=[
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_404_NOT_FOUND,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    async def patch_data(
        self,
        path: str,
        patch_document: JSONPatchDocument,
        transaction_id: Optional[str] = None,
    ):
        path = self._safe_data_module_path(path)
        # a patch document is a list of actions
        # we render each action with pydantic, and then dump the doc into json
        json_document = json.dumps([action.dict() for action in patch_document])

        async with aiohttp.ClientSession() as session:
            try:
                async with session.patch(
                    f"{self._opa_url}/data{path}",
                    data=json_document,
                    headers=self._headers,
                ) as opa_response:
                    return await proxy_response_unless_invalid(
                        opa_response, accepted_status_codes=[status.HTTP_204_NO_CONTENT]
                    )
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str) -> Dict:
        """
        wraps opa's "GET /data" api that extracts base data documents from opa cache.
        NOTE: opa always returns 200 and empty dict (for valid input) even if the data does not exist.

        returns a dict (parsed json).
        """
        # function accepts paths that start with / and also path that do not start with /
        if path.startswith("/"):
            path = path[1:]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._opa_url}/data/{path}", headers=self._headers
                ) as opa_response:
                    return await opa_response.json()
        except aiohttp.ClientError as e:
            logger.warning("Opa connection error: {err}", err=repr(e))
            raise

    @retry(**RETRY_CONFIG)
    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        """evaluates a data document against an input. that is how OPA "runs
        queries".

        see explanation how opa evaluate documents:
        https://www.openpolicyagent.org/docs/latest/philosophy/#the-opa-document-model

        see api reference:
        https://www.openpolicyagent.org/docs/latest/rest-api/#get-a-document-with-input
        """
        # opa data api format needs the input to sit under "input"
        opa_input = {"input": input.dict()}
        if path.startswith("/"):
            path = path[1:]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._opa_url}/data/{path}",
                    data=json.dumps(opa_input),
                    headers=self._headers,
                ) as opa_response:
                    return await proxy_response(opa_response)
        except aiohttp.ClientError as e:
            logger.warning("Opa connection error: {err}", err=repr(e))
            raise

    @retry(**RETRY_CONFIG)
    async def init_healthcheck_policy(
        self, policy_id: str, policy_code: str, data_updater_enabled: bool = True
    ):
        self._transaction_state = OpaTransactionLogState(
            policy_store=self,
            policy_id=policy_id,
            policy_template=policy_code,
            data_updater_enabled=data_updater_enabled,
        )
        return await self._transaction_state.persist()

    @retry(**RETRY_CONFIG)
    async def persist_transaction(self, transaction: StoreTransaction):
        if self._transaction_state is None:
            return
        self._transaction_state.process_transaction(transaction)
        return await self._transaction_state.persist()
