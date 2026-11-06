import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

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
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.logging_utils.errors import describe_error
from opal_common.schemas.policy import DataModule, PolicyBundle
from opal_common.schemas.store import StoreTransaction, TransactionType
from pydantic import BaseModel
from tenacity import retry

try:
    from openfga_sdk import ClientConfiguration, OpenFgaClient
    from openfga_sdk.client.models import (
        ClientCheckRequest,
        ClientExpandRequest,
        ClientTuple,
        ClientWriteRequest,
    )
    from openfga_sdk.credentials import CredentialConfiguration, Credentials

    HAS_OPENFGA_SDK = True
except ImportError:  # pragma: no cover
    ClientConfiguration = None  # type: ignore[assignment]
    OpenFgaClient = None  # type: ignore[assignment]
    ClientCheckRequest = None  # type: ignore[assignment]
    ClientExpandRequest = None  # type: ignore[assignment]
    ClientTuple = None  # type: ignore[assignment]
    ClientWriteRequest = None  # type: ignore[assignment]
    CredentialConfiguration = None  # type: ignore[assignment]
    Credentials = None  # type: ignore[assignment]
    HAS_OPENFGA_SDK = False


def parse_fga_dsl_to_json(dsl_text: str) -> Dict[str, Any]:
    """Convert a simple OpenFGA DSL (`model\\n  schema 1.1\\ntype ...`) or JSON
    string into an OpenFGA `WriteAuthorizationModelRequest` payload dict."""
    stripped = dsl_text.strip()
    if stripped.startswith("{"):
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict) or "type_definitions" not in parsed:
            raise ValueError(
                "OpenFGA JSON authorization model must contain 'type_definitions'."
            )
        parsed.setdefault("schema_version", "1.1")
        return parsed

    schema_match = re.search(r"schema\s+(\d+\.\d+)", stripped)
    if not schema_match:
        raise ValueError(
            "Invalid OpenFGA model: must be valid JSON or OpenFGA DSL containing 'schema <version>'."
        )
    schema_version = schema_match.group(1)
    type_definitions: List[Dict[str, Any]] = []

    current_type: Optional[Dict[str, Any]] = None
    in_relations = False

    for raw_line in stripped.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line == "model" or line.startswith("schema "):
            continue

        type_match = re.match(r"^type\s+([A-Za-z0-9_-]+)$", line)
        if type_match:
            if current_type is not None:
                type_definitions.append(current_type)
            current_type = {"type": type_match.group(1)}
            in_relations = False
            continue

        if line == "relations":
            if current_type is not None:
                current_type.setdefault("relations", {})
                current_type.setdefault("metadata", {"relations": {}})
                in_relations = True
            continue

        if in_relations and current_type is not None:
            rel_match = re.match(r"^define\s+([A-Za-z0-9_-]+)\s*:\s*(.+)$", line)
            if rel_match:
                rel_name, rel_expr = rel_match.group(1), rel_match.group(2).strip()
                current_type["relations"][rel_name] = {"this": {}}
                direct_types = re.findall(r"\[([^\]]+)\]", rel_expr)
                if direct_types:
                    type_refs = []
                    for group in direct_types:
                        for item in group.split(","):
                            t_name = item.strip()
                            if t_name:
                                type_refs.append({"type": t_name})
                    current_type["metadata"]["relations"][rel_name] = {
                        "directly_related_user_types": type_refs
                    }

    if current_type is not None:
        type_definitions.append(current_type)

    return {
        "schema_version": schema_version,
        "type_definitions": type_definitions,
    }


def normalize_tuple_key(tuple_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Extract canonical `{user, relation, object}` (+ optional `condition`)
    for OpenFGA tuple writes/deletes."""
    if "key" in tuple_obj and isinstance(tuple_obj["key"], dict):
        tuple_obj = tuple_obj["key"]
    normalized: Dict[str, Any] = {
        "user": str(tuple_obj["user"]),
        "relation": str(tuple_obj["relation"]),
        "object": str(tuple_obj["object"]),
    }
    if "condition" in tuple_obj and tuple_obj["condition"] is not None:
        normalized["condition"] = tuple_obj["condition"]
    return normalized


def normalize_openfga_write_payload(
    policy_data: JsonableValue,
    authorization_model_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Normalize incoming OPAL `policy_data` into an OpenFGA `/write` request
    body."""
    writes: List[Dict[str, Any]] = []
    deletes: List[Dict[str, Any]] = []

    if isinstance(policy_data, list):
        writes = [normalize_tuple_key(item) for item in policy_data if isinstance(item, dict)]
    elif isinstance(policy_data, dict):
        if "writes" in policy_data or "deletes" in policy_data:
            raw_writes = policy_data.get("writes")
            if isinstance(raw_writes, dict):
                raw_writes = raw_writes.get("tuple_keys", [])
            if isinstance(raw_writes, list):
                writes = [normalize_tuple_key(item) for item in raw_writes if isinstance(item, dict)]

            raw_deletes = policy_data.get("deletes")
            if isinstance(raw_deletes, dict):
                raw_deletes = raw_deletes.get("tuple_keys", [])
            if isinstance(raw_deletes, list):
                deletes = [normalize_tuple_key(item) for item in raw_deletes if isinstance(item, dict)]
        elif "tuples" in policy_data and isinstance(policy_data["tuples"], list):
            writes = [
                normalize_tuple_key(item)
                for item in policy_data["tuples"]
                if isinstance(item, dict)
            ]
        elif "tuple_keys" in policy_data and isinstance(policy_data["tuple_keys"], list):
            writes = [
                normalize_tuple_key(item)
                for item in policy_data["tuple_keys"]
                if isinstance(item, dict)
            ]
        elif all(k in policy_data for k in ("user", "relation", "object")):
            writes = [normalize_tuple_key(policy_data)]

    if not writes and not deletes:
        return None

    payload: Dict[str, Any] = {}
    if writes:
        payload["writes"] = {"tuple_keys": writes}
    if deletes:
        payload["deletes"] = {"tuple_keys": deletes}
    if authorization_model_id:
        payload["authorization_model_id"] = authorization_model_id
    return payload


def build_sdk_write_request(write_payload: Dict[str, Any]) -> Any:
    """Build an openfga_sdk ClientWriteRequest when SDK is available."""
    if not HAS_OPENFGA_SDK or ClientWriteRequest is None or ClientTuple is None:
        return write_payload

    writes_raw = (write_payload.get("writes") or {}).get("tuple_keys", [])
    deletes_raw = (write_payload.get("deletes") or {}).get("tuple_keys", [])
    writes = [
        ClientTuple(
            user=item["user"],
            relation=item["relation"],
            object=item["object"],
        )
        for item in writes_raw
    ]
    deletes = [
        ClientTuple(
            user=item["user"],
            relation=item["relation"],
            object=item["object"],
        )
        for item in deletes_raw
    ]
    kwargs: Dict[str, Any] = {}
    if writes:
        kwargs["writes"] = writes
    if deletes:
        kwargs["deletes"] = deletes
    return ClientWriteRequest(**kwargs)


class OpenFGAClient(LivenessProbeMixin, BasePolicyStoreClient):
    """OPAL Policy Store client for OpenFGA."""

    def __init__(
        self,
        openfga_server_url: Optional[str] = None,
        openfga_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        oauth_server: Optional[str] = None,
        store_id: Optional[str] = None,
        store_name: Optional[str] = None,
        authorization_model_id: Optional[str] = None,
        sdk_client: Optional[Any] = None,
    ):
        base_url = (
            openfga_server_url
            or opal_client_config.POLICY_STORE_URL
            or "http://localhost:8080"
        )
        self._openfga_url = base_url.rstrip("/")
        self._store_id: Optional[str] = (
            store_id
            if store_id is not None
            else getattr(opal_client_config, "OPENFGA_STORE_ID", None)
        )
        self._store_name: str = (
            store_name
            or getattr(opal_client_config, "OPENFGA_STORE_NAME", None)
            or "opal"
        )
        self._authorization_model_id: Optional[str] = (
            authorization_model_id
            if authorization_model_id is not None
            else getattr(opal_client_config, "OPENFGA_AUTHORIZATION_MODEL_ID", None)
        )
        self._policy_version: Optional[str] = None
        self._policies: Dict[str, str] = {}
        self._policy_models: Dict[str, str] = {}
        self._lock = asyncio.Lock()

        self._token = openfga_auth_token
        self._auth_type: PolicyStoreAuth = auth_type
        self._oauth_client_id = oauth_client_id
        self._oauth_client_secret = oauth_client_secret
        self._oauth_server = oauth_server
        self._sdk_client: Optional[Any] = sdk_client

        self._had_successful_data_transaction = False
        self._had_successful_policy_transaction = False
        self._most_recent_data_transaction: Optional[StoreTransaction] = None
        self._most_recent_policy_transaction: Optional[StoreTransaction] = None

        self._engine_reachable: bool = True
        self._init_liveness_probe()

        if auth_type == PolicyStoreAuth.TOKEN:
            if self._token is None:
                logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
                raise TypeError("required variables for token auth are not set")
        elif auth_type == PolicyStoreAuth.OAUTH:
            if (
                self._oauth_client_id is None
                or self._oauth_client_secret is None
                or self._oauth_server is None
            ):
                logger.error(
                    "POLICY_STORE_AUTH_OAUTH_SERVER, POLICY_STORE_AUTH_OAUTH_CLIENT_ID, "
                    "and POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET must be set for OAuth"
                )
                raise TypeError("required variables for oauth are not set")

        logger.info(f"Authentication mode for OpenFGA policy store: {auth_type}")

    def _build_sdk_configuration(self) -> Any:
        """Create an openfga_sdk ClientConfiguration for this store."""
        if not HAS_OPENFGA_SDK or ClientConfiguration is None:
            return None

        credentials = None
        if (
            self._auth_type == PolicyStoreAuth.TOKEN
            and self._token is not None
            and Credentials is not None
            and CredentialConfiguration is not None
        ):
            credentials = Credentials(
                method="api_token",
                configuration=CredentialConfiguration(api_token=self._token),
            )
        elif (
            self._auth_type == PolicyStoreAuth.OAUTH
            and Credentials is not None
            and CredentialConfiguration is not None
        ):
            credentials = Credentials(
                method="client_credentials",
                configuration=CredentialConfiguration(
                    api_issuer=self._oauth_server,
                    client_id=self._oauth_client_id,
                    client_secret=self._oauth_client_secret,
                ),
            )

        return ClientConfiguration(
            api_url=self._openfga_url,
            store_id=self._store_id,
            authorization_model_id=self._authorization_model_id,
            credentials=credentials,
        )

    def create_sdk_client(self) -> Optional[Any]:
        """Instantiate an official openfga_sdk OpenFgaClient when available."""
        if self._sdk_client is not None:
            return self._sdk_client
        if not HAS_OPENFGA_SDK or OpenFgaClient is None:
            return None
        config = self._build_sdk_configuration()
        return OpenFgaClient(config) if config is not None else None

    async def _get_auth_headers(
        self, session: Optional[aiohttp.ClientSession] = None
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        elif self._auth_type == PolicyStoreAuth.OAUTH:
            token = await self._fetch_oauth_token(session)
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _fetch_oauth_token(
        self, session: Optional[aiohttp.ClientSession] = None
    ) -> str:
        owns_session = session is None
        active_session = session or aiohttp.ClientSession(trust_env=True)
        try:
            async with active_session.post(
                self._oauth_server,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._oauth_client_id,
                    "client_secret": self._oauth_client_secret,
                },
            ) as res:
                res.raise_for_status()
                body = await res.json()
                self._token = body["access_token"]
                return self._token
        except aiohttp.ClientError as e:
            logger.warning(
                "OAuth server connection error: {err}", err=describe_error(e)
            )
            raise
        finally:
            if owns_session:
                await active_session.close()

    async def _ensure_store_id(
        self, session: aiohttp.ClientSession, headers: Dict[str, str]
    ) -> str:
        if self._store_id:
            return self._store_id

        async with self._lock:
            if self._store_id:
                return self._store_id

            async with session.get(
                f"{self._openfga_url}/stores", headers=headers
            ) as list_res:
                list_res.raise_for_status()
                stores_payload = await list_res.json()
                for store in stores_payload.get("stores", []):
                    if store.get("name") == self._store_name and store.get("id"):
                        self._store_id = store["id"]
                        return self._store_id

            async with session.post(
                f"{self._openfga_url}/stores",
                json={"name": self._store_name},
                headers=headers,
            ) as create_res:
                create_res.raise_for_status()
                created = await create_res.json()
                self._store_id = created["id"]
                return self._store_id

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
            logger.info(
                f"Ignoring setting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return Response(status_code=status.HTTP_200_OK)

        model_payload = parse_fga_dsl_to_json(policy_code)

        if self._sdk_client is not None:
            sdk_res = await self._sdk_client.write_authorization_model(model_payload)
            model_id = (
                getattr(sdk_res, "authorization_model_id", None)
                if not isinstance(sdk_res, dict)
                else sdk_res.get("authorization_model_id")
            )
            if model_id:
                self._authorization_model_id = model_id
                self._policy_version = model_id
                self._policy_models[policy_id] = model_id
            self._policies[policy_id] = policy_code
            return Response(status_code=status.HTTP_201_CREATED)

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers(session)
                store_id = await self._ensure_store_id(session, headers)
                async with session.post(
                    f"{self._openfga_url}/stores/{store_id}/authorization-models",
                    json=model_payload,
                    headers=headers,
                ) as openfga_response:
                    if 200 <= openfga_response.status < 300:
                        body = await openfga_response.json()
                        model_id = body.get("authorization_model_id")
                        if model_id:
                            self._authorization_model_id = model_id
                            self._policy_version = model_id
                            self._policy_models[policy_id] = model_id
                        self._policies[policy_id] = policy_code
                    return await proxy_response_unless_invalid(
                        openfga_response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_201_CREATED,
                            status.HTTP_400_BAD_REQUEST,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        if policy_id in self._policies:
            return self._policies[policy_id]

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers(session)
                store_id = await self._ensure_store_id(session, headers)
                model_id = self._policy_models.get(policy_id, policy_id)
                async with session.get(
                    f"{self._openfga_url}/stores/{store_id}/authorization-models/{model_id}",
                    headers=headers,
                ) as openfga_response:
                    if openfga_response.status == status.HTTP_404_NOT_FOUND:
                        return None
                    openfga_response.raise_for_status()
                    result = await openfga_response.json()
                    model = result.get("authorization_model")
                    return json.dumps(model) if model is not None else None
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers(session)
                store_id = await self._ensure_store_id(session, headers)
                async with session.get(
                    f"{self._openfga_url}/stores/{store_id}/authorization-models",
                    headers=headers,
                ) as openfga_response:
                    openfga_response.raise_for_status()
                    result = await openfga_response.json()
                    models = result.get("authorization_models", [])
                    policies = {
                        model["id"]: json.dumps(model)
                        for model in models
                        if isinstance(model, dict) and "id" in model
                    }
                    policies.update(self._policies)
                    return policies
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy_module_ids(self) -> List[str]:
        policies = await self.get_policies()
        return list((policies or {}).keys())

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy(
        self, policy_id: str, transaction_id: Optional[str] = None
    ):
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring deleting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        self._policies.pop(policy_id, None)
        removed_model_id = self._policy_models.pop(policy_id, None)
        if removed_model_id and self._authorization_model_id == removed_model_id:
            remaining = list(self._policy_models.values())
            self._authorization_model_id = remaining[-1] if remaining else None

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @affects_transaction
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ):
        if bundle.old_hash is None:
            await self._set_policies_from_complete_bundle(bundle)
        else:
            await self._set_policies_from_delta_bundle(bundle)

    async def _set_policies_from_complete_bundle(self, bundle: PolicyBundle):
        for module in bundle.data_modules:
            await self._set_policy_data_from_bundle_data_module(module)

        for policy in bundle.policy_modules:
            await self.set_policy(policy_id=policy.path, policy_code=policy.rego)

        current_ids = set(self._policies.keys())
        bundle_ids = {policy.path for policy in bundle.policy_modules}
        for deleted_id in current_ids - bundle_ids:
            await self.delete_policy(policy_id=deleted_id)

        self._policy_version = bundle.hash

    async def _set_policies_from_delta_bundle(self, bundle: PolicyBundle):
        for module in bundle.data_modules:
            await self._set_policy_data_from_bundle_data_module(module)

        for policy in bundle.policy_modules:
            await self.set_policy(policy_id=policy.path, policy_code=policy.rego)

        if bundle.deleted_files is not None:
            for deleted_data_path in bundle.deleted_files.data_modules:
                await self.delete_policy_data(
                    path=self._normalize_data_path(str(deleted_data_path))
                )
            for deleted_module_id in bundle.deleted_files.policy_modules:
                await self.delete_policy(policy_id=str(deleted_module_id))

        self._policy_version = bundle.hash

    @staticmethod
    def _normalize_data_path(path: str) -> str:
        if not path or path in (".", "/"):
            return ""
        return path if path.startswith("/") else f"/{path}"

    async def _set_policy_data_from_bundle_data_module(self, module: DataModule):
        module_path = self._normalize_data_path(module.path)
        try:
            module_data = json.loads(module.data)
            return await self.set_policy_data(
                policy_data=module_data,
                path=module_path,
            )
        except json.JSONDecodeError as e:
            logger.warning(
                "bundle contains non-json data module: {module_path}: {err}",
                module_path=module_path,
                err=describe_error(e),
            )

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        if policy_data is None:
            return Response(status_code=status.HTTP_200_OK)

        write_payload = normalize_openfga_write_payload(
            policy_data, authorization_model_id=self._authorization_model_id
        )
        if write_payload is None:
            return Response(status_code=status.HTTP_200_OK)

        if self._sdk_client is not None:
            sdk_req = build_sdk_write_request(write_payload)
            await self._sdk_client.write(sdk_req)
            return Response(status_code=status.HTTP_200_OK)

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers(session)
                store_id = await self._ensure_store_id(session, headers)
                async with session.post(
                    f"{self._openfga_url}/stores/{store_id}/write",
                    json=write_payload,
                    headers=headers,
                ) as openfga_response:
                    return await proxy_response_unless_invalid(
                        openfga_response,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_400_BAD_REQUEST,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ):
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers(session)
                store_id = await self._ensure_store_id(session, headers)

                read_body: Dict[str, Any] = {}
                cleaned_path = path.strip("/")
                if cleaned_path and ":" in cleaned_path:
                    read_body["tuple_key"] = {"object": cleaned_path}

                async with session.post(
                    f"{self._openfga_url}/stores/{store_id}/read",
                    json=read_body,
                    headers=headers,
                ) as read_res:
                    read_res.raise_for_status()
                    read_data = await read_res.json()

                tuples = read_data.get("tuples", [])
                tuple_keys = [
                    normalize_tuple_key(t["key"] if "key" in t else t)
                    for t in tuples
                    if isinstance(t, dict)
                ]
                if not tuple_keys:
                    return Response(status_code=status.HTTP_200_OK)

                delete_payload: Dict[str, Any] = {
                    "deletes": {"tuple_keys": tuple_keys}
                }
                if self._authorization_model_id:
                    delete_payload["authorization_model_id"] = (
                        self._authorization_model_id
                    )

                async with session.post(
                    f"{self._openfga_url}/stores/{store_id}/write",
                    json=delete_payload,
                    headers=headers,
                ) as write_res:
                    return await proxy_response_unless_invalid(
                        write_res,
                        accepted_status_codes=[
                            status.HTTP_200_OK,
                            status.HTTP_204_NO_CONTENT,
                            status.HTTP_404_NOT_FOUND,
                        ],
                    )
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str = "") -> Dict:
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers(session)
                store_id = await self._ensure_store_id(session, headers)
                read_body: Dict[str, Any] = {}
                cleaned_path = path.strip("/")
                if cleaned_path and ":" in cleaned_path:
                    read_body["tuple_key"] = {"object": cleaned_path}

                async with session.post(
                    f"{self._openfga_url}/stores/{store_id}/read",
                    json=read_body,
                    headers=headers,
                ) as openfga_response:
                    openfga_response.raise_for_status()
                    return await openfga_response.json()
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data_with_input(self, path: str, input: BaseModel) -> Dict:
        endpoint = path.strip("/") or "check"
        if endpoint not in ("check", "expand", "read"):
            endpoint = "check"

        input_dict = (
            input.model_dump(exclude_none=True)
            if hasattr(input, "model_dump")
            else input.dict(exclude_none=True)
        )
        if "tuple_key" not in input_dict and all(
            k in input_dict for k in ("user", "relation", "object")
        ):
            input_dict = {
                "tuple_key": {
                    "user": input_dict["user"],
                    "relation": input_dict["relation"],
                    "object": input_dict["object"],
                }
            }
        if (
            self._authorization_model_id
            and "authorization_model_id" not in input_dict
            and endpoint in ("check", "expand")
        ):
            input_dict["authorization_model_id"] = self._authorization_model_id

        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                headers = await self._get_auth_headers(session)
                store_id = await self._ensure_store_id(session, headers)
                async with session.post(
                    f"{self._openfga_url}/stores/{store_id}/{endpoint}",
                    json=input_dict,
                    headers=headers,
                ) as openfga_response:
                    openfga_response.raise_for_status()
                    return await openfga_response.json()
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    async def init_healthcheck_policy(self, policy_id: str, policy_code: str):
        return None

    async def log_transaction(self, transaction: StoreTransaction):
        if transaction.transaction_type == TransactionType.policy:
            self._most_recent_policy_transaction = transaction
            if transaction.success:
                self._had_successful_policy_transaction = True
        elif transaction.transaction_type == TransactionType.data:
            self._most_recent_data_transaction = transaction
            if transaction.success:
                self._had_successful_data_transaction = True

    async def is_ready(self) -> bool:
        return (
            self._had_successful_policy_transaction
            and self._had_successful_data_transaction
        )

    async def is_healthy(self) -> bool:
        transactions_healthy: bool = (
            self._most_recent_policy_transaction is not None
            and self._most_recent_policy_transaction.success
        ) and (
            self._most_recent_data_transaction is not None
            and self._most_recent_data_transaction.success
        )
        return transactions_healthy and self._engine_reachable

    @property
    def _probe_log_label(self) -> str:
        return "OpenFGA"

    async def _probe_engine_reachable(self, session: aiohttp.ClientSession) -> bool:
        """Issue a single GET against OpenFGA's `/healthz` endpoint."""
        health_url = f"{self._openfga_url}/healthz"
        async with session.get(health_url) as response:
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
        for policy_id, raw in (import_data.get("policies") or {}).items():
            await self.set_policy(policy_id=policy_id, policy_code=raw)

        raw_data = import_data.get("data")
        if raw_data:
            await self.set_policy_data(raw_data)

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version
