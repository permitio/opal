import asyncio
import functools
import json
import ssl
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from urllib.parse import urlencode

import aiohttp
import dpath
import jsonpatch
from aiofiles.threadpool.text import AsyncTextIOWrapper
from fastapi import Response, status
from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_client.policy_store.base_policy_store_client import (
    BasePolicyStoreClient,
    JsonableValue,
)
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_client.utils import exclude_none_fields, proxy_response
from opal_common.engine.parsing import get_rego_package
from opal_common.git_utils.bundle_utils import BundleUtils
from opal_common.paths import PathUtils
from opal_common.schemas.policy import DataModule, PolicyBundle, RegoModule
from opal_common.schemas.store import JSONPatchAction, StoreTransaction, TransactionType
from pydantic import BaseModel
from tenacity import RetryError, retry

JSONPatchDocument = List[JSONPatchAction]


RETRY_CONFIG = opal_client_config.POLICY_STORE_CONN_RETRY.toTenacityConfig()


def should_ignore_path(path, ignore_paths):
    """Helper function to check if the policy-store should ignore the given
    path."""
    paths_to_ignore = [p for p in ignore_paths if not p.startswith("!")]
    paths_to_not_ignore = [p[1:] for p in ignore_paths if p.startswith("!")]

    # Check if the path matches any path to not be ignored
    if PathUtils.glob_style_match_path_to_list(path, paths_to_not_ignore) is not None:
        return False

    # Check if the path matches any path to be ignored
    return PathUtils.glob_style_match_path_to_list(path, paths_to_ignore) is not None


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
    """Mark a method as write (affecting state of transaction) for transaction
    log."""
    setattr(func, "affects_transaction", True)
    return func


async def proxy_response_unless_invalid(
    raw_response: aiohttp.ClientResponse, accepted_status_codes: List[int]
) -> Response:
    """Throws value error if the http response received has an unexpected
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
    """Holds a mutatable state of the transaction log.

    can persist to OPA as hardcoded policy
    """

    POLICY_ACTIONS = ["set_policies", "set_policy", "delete_policy"]
    DATA_ACTIONS = ["set_policy_data", "delete_policy_data"]

    def __init__(
        self,
        data_updater_enabled: bool = True,
        policy_updater_enabled: bool = True,
    ):
        self._data_updater_disabled = not data_updater_enabled
        self._policy_updater_disabled = not policy_updater_enabled
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
        return is_ready

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
        is_healthy: bool = (
            self._policy_updater_disabled or policy_updater_is_healthy
        ) and (self._data_updater_disabled or data_updater_is_healthy)

        if is_healthy:
            logger.debug(
                f"OPA client health: {is_healthy} (policy: {policy_updater_is_healthy}, data: {data_updater_is_healthy})"
            )
        else:
            logger.warning(
                f"OPA client health: {is_healthy} (policy: {policy_updater_is_healthy}, data: {data_updater_is_healthy})"
            )

        return is_healthy

    @property
    def last_policy_transaction(self):
        if self._last_policy_transaction is None:
            return {}
        return self._last_policy_transaction.dict()

    @property
    def last_data_transaction(self):
        if self._last_data_transaction is None:
            return {}
        return self._last_data_transaction.dict()

    @property
    def last_failed_policy_transaction(self):
        if self._last_failed_policy_transaction is None:
            return {}
        return self._last_failed_policy_transaction.dict()

    @property
    def last_failed_data_transaction(self):
        if self._last_failed_data_transaction is None:
            return {}
        return self._last_failed_data_transaction.dict()

    @property
    def transaction_policy_statistics(self):
        return {
            "successful": self._num_successful_policy_transactions,
            "failed": self._num_failed_policy_transactions,
        }

    @property
    def transaction_data_statistics(self):
        return {
            "successful": self._num_successful_data_transactions,
            "failed": self._num_failed_data_transactions,
        }

    def _is_policy_transaction(self, transaction: StoreTransaction):
        return transaction.transaction_type == TransactionType.policy

    def _is_data_transaction(self, transaction: StoreTransaction):
        return transaction.transaction_type == TransactionType.data

    def process_transaction(self, transaction: StoreTransaction):
        """Mutates the state into a new state that can be then persisted as
        hardcoded policy."""
        logger.debug(
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


class OpaTransactionLogPolicyWriter:
    def __init__(
        self,
        policy_store: BasePolicyStoreClient,
        policy_id: str,
        policy_template: str,
    ):
        self._store = policy_store
        self._policy_id = policy_id
        self._policy_template = policy_template

    @staticmethod
    def _format_with_json(template, **kwargs):
        kwargs = {k: json.dumps(v) for k, v in kwargs.items()}
        return template.format(**kwargs)

    async def persist(self, state: OpaTransactionLogState):
        """Renders the policy template with the current state, and writes it to
        OPA."""
        logger.info(
            "persisting health check policy: ready={ready}, healthy={healthy}",
            ready=state.ready,
            healthy=state.healthy,
        )
        logger.info(
            "Policy and data statistics: policy: (successful {success_policy}, failed {failed_policy});\tdata: (successful {success_data}, failed {failed_data})",
            success_policy=state._num_successful_policy_transactions,
            failed_policy=state._num_failed_policy_transactions,
            success_data=state._num_successful_data_transactions,
            failed_data=state._num_failed_data_transactions,
        )
        policy_code = self._format_with_json(
            self._policy_template,
            ready=state.ready,
            healthy=state.healthy,
            last_policy_transaction=state.last_policy_transaction,
            last_failed_policy_transaction=state.last_failed_policy_transaction,
            last_data_transaction=state.last_data_transaction,
            last_failed_data_transaction=state.last_failed_data_transaction,
            transaction_data_statistics=state.transaction_data_statistics,
            transaction_policy_statistics=state.transaction_policy_statistics,
        )
        return await self._store.set_policy(
            policy_id=self._policy_id, policy_code=policy_code
        )


class OpaStaticDataCache:
    """Caching OPA's static data, so we can back it up without querying.

    /v1/data which also includes virtual documents.
    """

    def __init__(self):
        self._root_data = {}

    def set(self, path, data):
        if not path or path == "/":
            assert isinstance(data, dict), ValueError(
                "Setting root document must be a dict"
            )
            self._root_data = data.copy()
        else:
            # This would overwrite already existing paths
            dpath.new(self._root_data, path, data)

    def patch(self, path, data: List[JSONPatchAction]):
        for i, _ in enumerate(data):
            if not path == "/":
                data[i].path = path + data[i].path
        patch = jsonpatch.JsonPatch.from_string(json.dumps(exclude_none_fields(data)))
        patch.apply(self._root_data, in_place=True)

    def delete(self, path):
        if not path or path == "/":
            self._root_data = {}
        else:
            dpath.delete(self._root_data, path)

    def get_data(self):
        return self._root_data


class OpaClient(BasePolicyStoreClient):
    """Communicates with OPA via its REST API."""

    POLICY_NAME = "rbac"

    def __init__(
        self,
        opa_server_url=None,
        opa_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        oauth_server: Optional[str] = None,
        data_updater_enabled: bool = True,
        policy_updater_enabled: bool = True,
        cache_policy_data: bool = False,
        tls_client_cert: Optional[str] = None,
        tls_client_key: Optional[str] = None,
        tls_ca: Optional[str] = None,
    ):
        base_url = opa_server_url or opal_client_config.POLICY_STORE_URL
        self._opa_url = f"{base_url}/v1"
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()
        self._token = opa_auth_token
        self._auth_type: PolicyStoreAuth = auth_type
        self._oauth_client_id = oauth_client_id
        self._oauth_client_secret = oauth_client_secret
        self._oauth_server = oauth_server
        self._oauth_token_cache = {"token": None, "expires": 0}
        self._tls_client_cert = tls_client_cert
        self._tls_client_key = tls_client_key
        self._tls_ca = tls_ca

        if auth_type == PolicyStoreAuth.TOKEN:
            if self._token is None:
                logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
                raise Exception("required variables for token auth are not set")

        if auth_type == PolicyStoreAuth.OAUTH:
            isError = False
            if self._oauth_client_id is None:
                isError = True
                logger.error("POLICY_STORE_AUTH_OAUTH_CLIENT_ID can not be empty")

            if self._oauth_client_secret is None:
                isError = True
                logger.error("POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET can not be empty")

            if self._oauth_server is None:
                isError = True
                logger.error("POLICY_STORE_AUTH_OAUTH_SERVER can not be empty")

            if isError:
                raise Exception("required variables for oauth are not set")

        if auth_type == PolicyStoreAuth.TLS:
            isError = False
            if self._tls_client_cert is None:
                isError = True
                logger.error("POLICY_STORE_TLS_CLIENT_CERT can not be empty")

            if self._tls_client_key is None:
                isError = True
                logger.error("POLICY_STORE_TLS_CLIENT_KEY can not be empty")

            if self._tls_ca is None:
                isError = True
                logger.error("POLICY_STORE_TLS_CA can not be empty")

            if isError:
                raise Exception("required variables for tls are not set")

        logger.info(f"Authentication mode for policy store: {auth_type}")

        # custom SSL context
        self._custom_ssl_context = self._get_custom_ssl_context()
        self._ssl_context_kwargs = (
            {"ssl": self._custom_ssl_context}
            if self._custom_ssl_context is not None
            else {}
        )

        self._transaction_state = OpaTransactionLogState(
            data_updater_enabled=data_updater_enabled,
            policy_updater_enabled=policy_updater_enabled,
        )
        # as long as this is null, persisting transaction log to OPA is disabled
        self._transaction_state_writer: Optional[OpaTransactionLogState] = None

        self._policy_data_cache: Optional[OpaStaticDataCache] = None
        if cache_policy_data:
            self._policy_data_cache = OpaStaticDataCache()

    def _get_custom_ssl_context(self) -> Optional[ssl.SSLContext]:
        if not self._tls_ca:
            return None

        ssl_context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH, cafile=self._tls_ca
        )

        if self._tls_client_key and self._tls_client_cert:
            ssl_context.load_cert_chain(
                certfile=self._tls_client_cert, keyfile=self._tls_client_key
            )

        return ssl_context

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    @retry(**RETRY_CONFIG)
    async def _get_oauth_token(self):
        logger.info("Retrieving a new OAuth access_token.")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self._oauth_server,
                    headers={
                        "accept": "application/json",
                        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
                    },
                    data=urlencode({"grant_type": "client_credentials"}).encode(
                        "utf-8"
                    ),
                    auth=aiohttp.BasicAuth(
                        self._oauth_client_id, self._oauth_client_secret
                    ),
                ) as oauth_response:
                    response = await oauth_response.json()
                    logger.info(
                        f"got access_token, expires in {response['expires_in']} seconds"
                    )

                    return {
                        # refresh token before it expires, lets subtract 10 seconds
                        "expires": time.time() + response["expires_in"] - 10,
                        "token": response["access_token"],
                    }
            except aiohttp.ClientError as e:
                logger.warning("OAuth server connection error: {err}", err=repr(e))
                raise

    async def _get_auth_headers(self) -> {}:
        headers = {}
        if self._auth_type == PolicyStoreAuth.TOKEN:
            if self._token is not None:
                headers.update({"Authorization": f"Bearer {self._token}"})

        elif self._auth_type == PolicyStoreAuth.OAUTH:
            if (
                self._oauth_token_cache["token"] is None
                or time.time() > self._oauth_token_cache["expires"]
            ):
                self._oauth_token_cache = await self._get_oauth_token()

            headers.update(
                {"Authorization": f"Bearer {self._oauth_token_cache['token']}"}
            )

        return headers

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        # ignore explicitly configured paths
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring setting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return
        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()

                async with session.put(
                    f"{self._opa_url}/policies/{policy_id}",
                    data=policy_code,
                    headers={"content-type": "text/plain", **headers},
                    **self._ssl_context_kwargs,
                ) as opa_response:
                    return await proxy_response_unless_invalid(
                        opa_response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            # No point in immediate retry, this means erroneous rego (bad syntax, duplicated definition, etc)
                            status.HTTP_400_BAD_REQUEST,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()

                async with session.get(
                    f"{self._opa_url}/policies/{policy_id}",
                    headers=headers,
                    **self._ssl_context_kwargs,
                ) as opa_response:
                    result = await opa_response.json()
                    return result.get("result", {}).get("raw", None)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()

                async with session.get(
                    f"{self._opa_url}/policies",
                    headers=headers,
                    **self._ssl_context_kwargs,
                ) as opa_response:
                    result = await opa_response.json()
                    return OpaClient._extract_modules_from_policies_json(result)
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        # ignore explicitly configured paths
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring deleting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return

        async with aiohttp.ClientSession() as session:
            try:
                headers = await self._get_auth_headers()

                async with session.delete(
                    f"{self._opa_url}/policies/{policy_id}",
                    headers=headers,
                    **self._ssl_context_kwargs,
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

    async def get_policy_module_ids(self) -> List[str]:
        modules = await self.get_policies()
        return modules.keys()

    @staticmethod
    def _extract_modules_from_policies_json(result: Dict[str, Any]) -> Dict[str, str]:
        """return all module ids in OPA cache who are not:

        - skipped module ids (i.e: our health check policy)
        - all modules with package name starting with "system" (special OPA policies)
        """
        policies: List[Dict[str, Any]] = result.get("result", [])
        builtin_modules = [opal_client_config.OPA_HEALTH_CHECK_POLICY_PATH]

        modules = {}
        for policy in policies:
            module_id = policy.get("id", None)
            module_raw = policy.get("raw", "")
            package_name = get_rego_package(module_raw)

            if module_id is None:
                continue

            if package_name is not None and package_name.startswith("system."):
                continue

            if module_id in builtin_modules:
                continue

            modules[module_id] = module_raw

        return modules

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        if bundle.old_hash is None:
            return await self._set_policies_from_complete_bundle(bundle)
        else:
            return await self._set_policies_from_delta_bundle(bundle)

    @staticmethod
    async def _attempt_operations_with_postponed_failure_retry(
        ops: List[Callable[[], Awaitable[Response]]]
    ):
        """Attempt to execute the given operations in the given order, where
        failed operations are tried again at the end (recursively).

        This overcomes issues of misordering (e.g. setting a renamed
        policy before deleting the old one, or setting a policy before
        its dependencies)
        """
        while True:
            failed_ops = []
            failure_msgs = []
            for op in ops:
                # Only expected errors are retried (such as 400), so exceptions are not caught
                response = await op()
                if response and response.status_code != status.HTTP_200_OK:
                    # Delay error logging until we know retrying won't help
                    failure_msgs.append(
                        f"Failed policy operation. status: {response.status_code}, body: {response.body.decode()}"
                    )
                    failed_ops.append(op)

            if len(failed_ops) == 0:
                # all ops succeeded
                return

            if len(failed_ops) == len(ops):
                # all ops failed on this iteration, no point at retrying
                for failure_msg in failure_msgs:
                    logger.error(failure_msg)

                raise RuntimeError("Giving up setting / deleting failed modules to OPA")

            ops = failed_ops  # retry failed ops

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
            await OpaClient._attempt_operations_with_postponed_failure_retry(
                [
                    functools.partial(
                        self.set_policy, policy_id=module.path, policy_code=module.rego
                    )
                    for module in BundleUtils.sorted_policy_modules_to_load(bundle)
                ]
            )

            # remove policies from the store that are not in the bundle
            # (because this bundle is "complete", i.e: contains all policy modules for a given hash)
            # Note: this can be ignored below by config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
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

            # remove static policy data from store
            for module_id in BundleUtils.sorted_data_modules_to_delete(bundle):
                await self.delete_policy_data(
                    path=self._safe_data_module_path(str(module_id))
                )

            await OpaClient._attempt_operations_with_postponed_failure_retry(
                # save bundled policies into store
                [
                    functools.partial(
                        self.set_policy, policy_id=module.path, policy_code=module.rego
                    )
                    for module in BundleUtils.sorted_policy_modules_to_load(bundle)
                ]
                + [
                    # remove deleted policies from store
                    functools.partial(self.delete_policy, policy_id=module_id)
                    for module_id in BundleUtils.sorted_policy_modules_to_delete(bundle)
                ]
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
                headers = await self._get_auth_headers()
                data = json.dumps(exclude_none_fields(policy_data))
                async with session.put(
                    f"{self._opa_url}/data{path}",
                    data=data,
                    headers=headers,
                    **self._ssl_context_kwargs,
                ) as opa_response:
                    response = await proxy_response_unless_invalid(
                        opa_response,
                        accepted_status_codes=[
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_304_NOT_MODIFIED,
                        ],
                    )
                    if self._policy_data_cache:
                        self._policy_data_cache.set(path, json.loads(data))
                    return response
            except aiohttp.ClientError as e:
                logger.warning("Opa connection error: {err}", err=repr(e))
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def patch_policy_data(
        self,
        policy_data: List[JSONPatchAction],
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
                headers = await self._get_auth_headers()
                headers["Content-Type"] = "application/json-patch+json"

                async with session.patch(
                    f"{self._opa_url}/data{path}",
                    data=json.dumps(exclude_none_fields(policy_data)),
                    headers=headers,
                    **self._ssl_context_kwargs,
                ) as opa_response:
                    response = await proxy_response_unless_invalid(
                        opa_response,
                        accepted_status_codes=[
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_304_NOT_MODIFIED,
                        ],
                    )
                    if self._policy_data_cache:
                        self._policy_data_cache.patch(path, policy_data)
                    return response
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
                headers = await self._get_auth_headers()

                async with session.delete(
                    f"{self._opa_url}/data{path}",
                    headers=headers,
                    **self._ssl_context_kwargs,
                ) as opa_response:
                    response = await proxy_response_unless_invalid(
                        opa_response,
                        accepted_status_codes=[
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_404_NOT_FOUND,
                        ],
                    )
                    if self._policy_data_cache:
                        self._policy_data_cache.delete(path)
                    return response
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
        if path != "" and not path.startswith("/"):
            path = "/" + path
        try:
            headers = await self._get_auth_headers()

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._opa_url}/data{path}",
                    headers=headers,
                    **self._ssl_context_kwargs,
                ) as opa_response:
                    json_response = await opa_response.json()
                    return json_response.get("result", {})
        except aiohttp.ClientError as e:
            logger.warning("Opa connection error: {err}", err=repr(e))
            raise

    @retry(**RETRY_CONFIG)
    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        """Evaluates a data document against an input. that is how OPA "runs
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
            headers = await self._get_auth_headers()

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._opa_url}/data/{path}",
                    data=json.dumps(opa_input),
                    headers=headers,
                    **self._ssl_context_kwargs,
                ) as opa_response:
                    return await proxy_response(opa_response)
        except aiohttp.ClientError as e:
            logger.warning("Opa connection error: {err}", err=repr(e))
            raise

    @retry(**RETRY_CONFIG)
    async def init_healthcheck_policy(self, policy_id: str, policy_code: str):
        self._transaction_state_writer = OpaTransactionLogPolicyWriter(
            policy_store=self,
            policy_id=policy_id,
            policy_template=policy_code,
        )
        return await self._transaction_state_writer.persist(self._transaction_state)

    @retry(**RETRY_CONFIG)
    async def log_transaction(self, transaction: StoreTransaction):
        self._transaction_state.process_transaction(transaction)

        if self._transaction_state_writer:
            try:
                return await self._transaction_state_writer.persist(
                    self._transaction_state
                )
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

    async def is_ready(self) -> bool:
        return self._transaction_state.ready

    async def is_healthy(self) -> bool:
        return self._transaction_state.healthy

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        policies = await self.get_policies()
        data = self._policy_data_cache.get_data()
        await writer.write(
            json.dumps({"policies": policies, "data": data}, default=str)
        )

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        import_data = json.loads(await reader.read())

        await OpaClient._attempt_operations_with_postponed_failure_retry(
            [
                functools.partial(self.set_policy, policy_id=id, policy_code=raw)
                for id, raw in import_data["policies"].items()
            ]
        )

        await self.set_policy_data(import_data["data"])
