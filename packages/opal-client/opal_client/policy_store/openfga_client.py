import asyncio
import json
from typing import Any, Dict, List, Optional

import aiohttp
from aiofiles.threadpool.text import AsyncTextIOWrapper
from fastapi import Response, status
from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_client.policy_store.base_policy_store_client import (
    BasePolicyStoreClient,
    JsonableValue,
)
from opal_client.policy_store.liveness_probe import LivenessProbeMixin
from opal_client.policy_store.opa_client import (
    RETRY_CONFIG,
    affects_transaction,
    fail_silently,
    proxy_response_unless_invalid,
    should_ignore_path,
)
from opal_client.policy_store.openfga_dsl import parse_fga_dsl_to_json
from opal_client.policy_store.openfga_tuples import (
    extract_read_tuples,
    filter_tuples_by_path,
    normalize_openfga_write_payload,
)
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.logging_utils.errors import describe_error
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.store import StoreTransaction, TransactionType
from pydantic import BaseModel
from tenacity import retry

__all__ = [
    "OpenFGAClient",
    "parse_fga_dsl_to_json",
    "normalize_openfga_write_payload",
]


def _validate_openfga_auth_config(
    auth_type: PolicyStoreAuth, credentials: Dict[str, Optional[str]]
) -> None:
    if auth_type == PolicyStoreAuth.TOKEN and not credentials.get("token"):
        logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
        raise TypeError("required variables for token auth are not set")
    if auth_type == PolicyStoreAuth.OAUTH and not _has_oauth_credentials(credentials):
        raise TypeError("required variables for oauth are not set")


def _has_oauth_credentials(credentials: Dict[str, Optional[str]]) -> bool:
    for key in ("oauth_client_id", "oauth_client_secret", "oauth_server"):
        if not credentials.get(key):
            return False
    return True


def _extract_input_dict(input_data: BaseModel) -> Dict[str, Any]:
    if hasattr(input_data, "model_dump"):
        return input_data.model_dump(exclude_none=True)
    return input_data.dict(exclude_none=True)


# Policy store client managing OpenFGA authorization models and relationship tuples.
class OpenFGAClient(LivenessProbeMixin, BasePolicyStoreClient):
    def __init__(
        self,
        openfga_server_url: Optional[str] = None,
        openfga_auth_token: Optional[str] = None,
        **kwargs: Any,
    ):
        base_url = openfga_server_url or opal_client_config.POLICY_STORE_URL
        self._base_url = base_url.rstrip("/")
        self._auth_type: PolicyStoreAuth = kwargs.get(
            "auth_type", PolicyStoreAuth.NONE
        )
        self._token = openfga_auth_token
        self._oauth_client_id: Optional[str] = kwargs.get("oauth_client_id")
        self._oauth_client_secret: Optional[str] = kwargs.get("oauth_client_secret")
        self._oauth_server: Optional[str] = kwargs.get("oauth_server")
        self._store_id: Optional[str] = kwargs.get(
            "store_id", opal_client_config.OPENFGA_STORE_ID
        )
        self._store_name: str = (
            kwargs.get("store_name") or opal_client_config.OPENFGA_STORE_NAME or "opal"
        )
        self._authorization_model_id: Optional[str] = kwargs.get(
            "authorization_model_id",
            opal_client_config.OPENFGA_AUTHORIZATION_MODEL_ID,
        )
        self._policy_version: Optional[str] = None
        self._policy_models: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._had_successful_data_transaction = False
        self._had_successful_policy_transaction = False
        self._most_recent_data_transaction: Optional[StoreTransaction] = None
        self._most_recent_policy_transaction: Optional[StoreTransaction] = None
        self._engine_reachable: bool = True
        self._init_liveness_probe()
        _validate_openfga_auth_config(
            self._auth_type,
            {
                "token": self._token,
                "oauth_client_id": self._oauth_client_id,
                "oauth_client_secret": self._oauth_client_secret,
                "oauth_server": self._oauth_server,
            },
        )

    async def _get_auth_headers(self) -> Dict[str, str]:
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            return {"Authorization": f"Bearer {self._token}"}
        if self._auth_type == PolicyStoreAuth.OAUTH:
            token = await self._fetch_oauth_token()
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def _fetch_oauth_token(self) -> str:
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._oauth_client_id,
            "client_secret": self._oauth_client_secret,
        }
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(str(self._oauth_server), data=payload) as resp:
                resp.raise_for_status()
                body = await resp.json()
                return str(body["access_token"])

    async def _ensure_store_id(self, session: aiohttp.ClientSession) -> str:
        if self._store_id:
            return self._store_id
        headers = await self._get_auth_headers()
        existing_id = await self._find_store_by_name(session, headers)
        if existing_id:
            self._store_id = existing_id
            return existing_id
        created_id = await self._create_store(session, headers)
        self._store_id = created_id
        return created_id

    async def _find_store_by_name(
        self, session: aiohttp.ClientSession, headers: Dict[str, str]
    ) -> Optional[str]:
        async with session.get(f"{self._base_url}/stores", headers=headers) as resp:
            if resp.status >= 400:
                resp.raise_for_status()
            data = await resp.json()
            for store in data.get("stores", []):
                if store.get("name") == self._store_name:
                    return str(store["id"])
        return None

    async def _create_store(
        self, session: aiohttp.ClientSession, headers: Dict[str, str]
    ) -> str:
        async with session.post(
            f"{self._base_url}/stores",
            json={"name": self._store_name},
            headers=headers,
        ) as resp:
            if resp.status >= 400:
                resp.raise_for_status()
            created = await resp.json()
            return str(created["id"])

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            return None
        model_payload = parse_fga_dsl_to_json(policy_code)
        return await self._post_authorization_model(
            (policy_id, policy_code), model_payload
        )

    async def _post_authorization_model(
        self, policy_meta: tuple[str, str], model_payload: Dict[str, Any]
    ) -> Response:
        policy_id, policy_code = policy_meta
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()
                url = f"{self._base_url}/stores/{store_id}/authorization-models"
                async with session.post(
                    url, json=model_payload, headers=headers
                ) as response:
                    await self._record_created_model(
                        response, (policy_id, policy_code)
                    )
                    return await proxy_response_unless_invalid(
                        response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_201_CREATED,
                            status.HTTP_400_BAD_REQUEST,
                        ],
                    )
        except aiohttp.ClientError as err:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(err))
            raise

    async def _record_created_model(
        self, response: aiohttp.ClientResponse, policy_meta: tuple[str, str]
    ) -> None:
        if response.status not in (status.HTTP_200_OK, status.HTTP_201_CREATED):
            return
        policy_id, policy_code = policy_meta
        try:
            payload = await response.json()
            model_id = payload.get("authorization_model_id")
            if model_id:
                self._authorization_model_id = str(model_id)
        except Exception:
            pass
        self._policy_models[policy_id] = policy_code

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        if policy_id in self._policy_models:
            return self._policy_models[policy_id]
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()
                model_id = policy_id or self._authorization_model_id
                url = self._build_model_get_url(store_id, model_id)
                async with session.get(url, headers=headers) as response:
                    if response.status >= 400:
                        response.raise_for_status()
                    data = await response.json()
                    model = data.get("authorization_model")
                    if model is None:
                        models = data.get("authorization_models", [])
                        model = models[0] if models else None
                    return json.dumps(model) if model is not None else None
        except aiohttp.ClientError as err:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(err))
            raise

    def _build_model_get_url(
        self, store_id: str, model_id: Optional[str]
    ) -> str:
        base = f"{self._base_url}/stores/{store_id}/authorization-models"
        return f"{base}/{model_id}" if model_id else base

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()
                url = f"{self._base_url}/stores/{store_id}/authorization-models"
                async with session.get(url, headers=headers) as response:
                    if response.status >= 400:
                        response.raise_for_status()
                    data = await response.json()
                    models = data.get("authorization_models", [])
                    return {
                        str(m.get("id", idx)): json.dumps(m)
                        for idx, m in enumerate(models)
                    }
        except aiohttp.ClientError as err:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(err))
            raise

    async def get_policy_module_ids(self) -> List[str]:
        if self._policy_models:
            return list(self._policy_models.keys())
        policies = await self.get_policies()
        return list(policies.keys()) if policies else []

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy(
        self, policy_id: str, transaction_id: Optional[str] = None
    ):
        self._policy_models.pop(policy_id, None)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        for module in bundle.policy_modules:
            await self.set_policy(module.path, module.rego)
        if bundle.deleted_files is not None:
            for deleted in bundle.deleted_files.policy_modules:
                await self.delete_policy(str(deleted))
        self._policy_version = bundle.hash

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        write_payload = normalize_openfga_write_payload(
            policy_data, self._authorization_model_id
        )
        if write_payload is None:
            return Response(status_code=status.HTTP_200_OK)
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()
                url = f"{self._base_url}/stores/{store_id}/write"
                async with session.post(
                    url, json=write_payload, headers=headers
                ) as response:
                    return await proxy_response_unless_invalid(
                        response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_400_BAD_REQUEST,
                        ],
                    )
        except aiohttp.ClientError as err:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(err))
            raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()
                tuples = await self._read_raw_tuples(session, (store_id, headers))
                matched = filter_tuples_by_path(tuples, path)
                if not matched:
                    return Response(status_code=status.HTTP_204_NO_CONTENT)
                delete_body: Dict[str, Any] = {"deletes": {"tuple_keys": matched}}
                if self._authorization_model_id:
                    delete_body["authorization_model_id"] = (
                        self._authorization_model_id
                    )
                url = f"{self._base_url}/stores/{store_id}/write"
                async with session.post(
                    url, json=delete_body, headers=headers
                ) as response:
                    return await proxy_response_unless_invalid(
                        response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_404_NOT_FOUND,
                        ],
                    )
        except aiohttp.ClientError as err:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(err))
            raise

    async def _read_raw_tuples(
        self,
        session: aiohttp.ClientSession,
        store_ctx: tuple[str, Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        store_id, headers = store_ctx
        url = f"{self._base_url}/stores/{store_id}/read"
        async with session.post(url, json={}, headers=headers) as response:
            if response.status >= 400:
                response.raise_for_status()
            payload = await response.json()
            return extract_read_tuples(payload)

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str = "") -> Dict:
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()
                tuples = await self._read_raw_tuples(session, (store_id, headers))
                return {"tuples": filter_tuples_by_path(tuples, path)}
        except aiohttp.ClientError as err:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(err))
            raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        input_dict = _extract_input_dict(input)
        endpoint = "expand" if path.strip("/") == "expand" else "check"
        body = self._build_query_body(endpoint, input_dict)
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()
                url = f"{self._base_url}/stores/{store_id}/{endpoint}"
                async with session.post(url, json=body, headers=headers) as resp:
                    if resp.status >= 400:
                        resp.raise_for_status()
                    return await resp.json()
        except aiohttp.ClientError as err:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(err))
            raise

    def _build_query_body(
        self, endpoint: str, input_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        if "tuple_key" in input_dict:
            body = dict(input_dict)
        elif endpoint == "expand":
            body = {
                "tuple_key": {
                    "relation": input_dict.get("relation"),
                    "object": input_dict.get("object"),
                }
            }
        else:
            body = {
                "tuple_key": {
                    "user": input_dict.get("user"),
                    "relation": input_dict.get("relation"),
                    "object": input_dict.get("object"),
                }
            }
        if self._authorization_model_id and "authorization_model_id" not in body:
            body["authorization_model_id"] = self._authorization_model_id
        return body

    async def init_healthcheck_policy(self, policy_id: str, policy_code: str):
        return None

    async def log_transaction(self, transaction: StoreTransaction):
        if transaction.transaction_type == TransactionType.policy:
            self._record_policy_transaction(transaction)
            return
        if transaction.transaction_type == TransactionType.data:
            self._record_data_transaction(transaction)

    def _record_policy_transaction(self, transaction: StoreTransaction) -> None:
        self._most_recent_policy_transaction = transaction
        if transaction.success:
            self._had_successful_policy_transaction = True

    def _record_data_transaction(self, transaction: StoreTransaction) -> None:
        self._most_recent_data_transaction = transaction
        if transaction.success:
            self._had_successful_data_transaction = True

    async def is_ready(self) -> bool:
        return (
            self._had_successful_policy_transaction
            and self._had_successful_data_transaction
        )

    async def is_healthy(self) -> bool:
        policy_ok = (
            self._most_recent_policy_transaction is not None
            and self._most_recent_policy_transaction.success
        )
        data_ok = (
            self._most_recent_data_transaction is not None
            and self._most_recent_data_transaction.success
        )
        return policy_ok and data_ok and self._engine_reachable

    @property
    def _probe_log_label(self) -> str:
        return "OpenFGA"

    async def _probe_engine_reachable(self, session: aiohttp.ClientSession) -> bool:
        async with session.get(f"{self._base_url}/healthz") as response:
            return 200 <= response.status < 300

    def _set_engine_reachable(self, value: bool) -> None:
        self._engine_reachable = value

    def _get_engine_reachable(self) -> bool:
        return self._engine_reachable

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        policies = await self.get_policies()
        data = await self.get_data("")
        await writer.write(
            json.dumps({"policies": policies, "data": data}, default=str)
        )

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        import_data = json.loads(await reader.read())
        for policy_id, raw_model in (import_data.get("policies") or {}).items():
            await self.set_policy(policy_id=policy_id, policy_code=raw_model)
        if "data" in import_data:
            await self.set_policy_data(import_data["data"])
