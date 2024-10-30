import asyncio
import json
from typing import Dict, List, Optional, Any, Set, Union
from datetime import datetime
import uuid

import aiohttp
from aiofiles.threadpool.text import AsyncTextIOWrapper
from fastapi import Response, status
from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_client.policy_store.base_policy_store_client import (
    BasePolicyStoreClient,
    JsonableValue,
)
from opal_client.policy_store.opa_client import (
    RETRY_CONFIG,
    affects_transaction,
    fail_silently,
    proxy_response_unless_invalid,
    should_ignore_path,
)
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_common.schemas.policy import PolicyBundle
from opal_common.schemas.store import StoreTransaction, TransactionType
from tenacity import retry

class OpenFGATransactionLogState:
    """State tracker for OpenFGA transactions and health checks."""
    
    def __init__(
        self,
        data_updater_enabled: bool = True,
        policy_updater_enabled: bool = True,
    ):
        self._data_updater_disabled = not data_updater_enabled
        self._policy_updater_disabled = not policy_updater_enabled
        
        # Transaction tracking
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
        """System is ready if it has had successful transactions or updaters are disabled."""
        is_ready = (
            (self._policy_updater_disabled or self._num_successful_policy_transactions > 0) and
            (self._data_updater_disabled or self._num_successful_data_transactions > 0)
        )
        return is_ready

    @property
    def healthy(self) -> bool:
        """System is healthy if latest transactions were successful."""
        if not self.ready:
            return False
            
        policy_healthy = (
            self._policy_updater_disabled or 
            (self._last_policy_transaction is not None and 
            self._last_policy_transaction.success)
        )
        
        data_healthy = (
            self._data_updater_disabled or
            (self._last_data_transaction is not None and 
            self._last_data_transaction.success)
        )
        
        is_healthy = policy_healthy and data_healthy

        if is_healthy:
            logger.debug(
                f"OpenFGA client health: healthy=True (policy={policy_healthy}, data={data_healthy})"
            )
        else:
            logger.warning(
                f"OpenFGA client health: healthy=False (policy={policy_healthy}, data={data_healthy})"
            )

        return is_healthy

    def process_transaction(self, transaction: StoreTransaction):
        """Process and track transaction state."""
        logger.debug(
            "processing store transaction: {transaction}",
            transaction=transaction.dict(),
        )

        if transaction.transaction_type == TransactionType.policy:
            self._last_policy_transaction = transaction
            if transaction.success:
                self._num_successful_policy_transactions += 1
            else:
                self._last_failed_policy_transaction = transaction
                self._num_failed_policy_transactions += 1
            
        elif transaction.transaction_type == TransactionType.data:
            self._last_data_transaction = transaction
            if transaction.success:
                self._num_successful_data_transactions += 1
            else:
                self._last_failed_data_transaction = transaction
                self._num_failed_data_transactions += 1
                
# Defines the authorization model for healthcheck data
HEALTHCHECK_AUTHORIZATION_MODEL = {
    "schema_version": "1.1",
    "type_definitions": [
        {
            "type": "healthcheck",
            "relations": {
                "reader": {
                    "this": {}
                },
                "writer": {
                    "this": {}
                }
            }
        },
        {
            "type": "transaction_state",
            "relations": {
                "reader": {  
                    "this": {}
                },
                "writer": {
                    "this": {}
                }
            }
        }
    ]
}

class OpenFGATransactionLogPolicyWriter:
    """Manages transaction logs for OpenFGA policy store."""
    
    def __init__(
        self,
        policy_store: BasePolicyStoreClient,
        store_id: str,
    ):
        self._store = policy_store
        self._store_id = store_id

    async def initialize(self):
        """Initialize the authorization model for healthcheck."""
        try:
            await self._store.set_policy(
                "healthcheck_model",
                json.dumps(HEALTHCHECK_AUTHORIZATION_MODEL)
            )
        except Exception as e:
            logger.error(f"Failed to initialize healthcheck model: {str(e)}")
            raise

    async def persist(self, state: OpenFGATransactionLogState):
        """Persist the transaction state using OpenFGA's authorization model format."""
        logger.info(
            "persisting health check state: ready={ready}, healthy={healthy}",
            ready=state.ready,
            healthy=state.healthy,
        )
        logger.info(
            "Policy and data statistics: policy: (successful {success_policy}, failed {failed_policy});\t"
            "data: (successful {success_data}, failed {failed_data})",
            success_policy=state._num_successful_policy_transactions,
            failed_policy=state._num_failed_policy_transactions,
            success_data=state._num_successful_data_transactions,
            failed_data=state._num_failed_data_transactions,
        )

        # Structure transaction state data
        state_data = {
            "ready": state.ready,
            "healthy": state.healthy,
            "last_policy_transaction": self._get_transaction_data(state._last_policy_transaction),
            "last_failed_policy_transaction": self._get_transaction_data(state._last_failed_policy_transaction),
            "last_data_transaction": self._get_transaction_data(state._last_data_transaction),
            "last_failed_data_transaction": self._get_transaction_data(state._last_failed_data_transaction),
            "transaction_statistics": {
                "policy": {
                    "successful": state._num_successful_policy_transactions,
                    "failed": state._num_failed_policy_transactions
                },
                "data": {
                    "successful": state._num_successful_data_transactions,
                    "failed": state._num_failed_data_transactions
                }
            }
        }

        # Create OpenFGA tuples
        tuples = [
            {
                "user": self._store_id,
                "relation": "writer",
                "object": "transaction_state:current",
                "condition": {
                    "context": state_data
                }
            },
            {
                "user": self._store_id, 
                "relation": "reader",
                "object": "transaction_state:current"
            }
        ]

        try:
            await self._store.set_policy_data({"tuples": tuples})
            logger.debug("Successfully persisted transaction state")
            return True
        except Exception as e:
            logger.error(f"Failed to persist transaction state: {str(e)}")
            return False

    def _get_transaction_data(self, transaction: Optional[StoreTransaction]) -> Dict:
        """Helper to extract data from a transaction object."""
        if transaction is None:
            return {}
            
        return {
            "id": transaction.id,
            "transaction_type": transaction.transaction_type.value if transaction.transaction_type else None,
            "actions": transaction.actions,
            "success": transaction.success,
            "error": transaction.error,
            "creation_time": transaction.creation_time,
            "end_time": transaction.end_time
        }

    async def get_transaction_state(self) -> Dict:
        """Retrieve the current transaction state."""
        try:
            state = await self._store.get_data("transaction_state:current")
            if state and "tuples" in state:
                for tuple in state["tuples"]:
                    if tuple.get("relation") == "writer":
                        return tuple.get("condition", {}).get("context", {})
            return {}
        except Exception as e:
            logger.error(f"Failed to retrieve transaction state: {str(e)}")
            return {}        


class OpenFGAStaticDataCache:
    """Cache for OpenFGA relationship tuples."""
    
    def __init__(self):
        self._tuples = []

    def set(self, tuples: List[Dict[str, str]]):
        """Set relationship tuples in cache."""
        self._tuples = [tuple.copy() for tuple in tuples]

    def patch(self, tuples: List[Dict[str, str]]):
        """Add or update tuples in cache."""
        existing_keys = set((t["user"], t["relation"], t["object"]) for t in self._tuples)
        
        for new_tuple in tuples:
            key = (new_tuple["user"], new_tuple["relation"], new_tuple["object"])
            if key not in existing_keys:
                self._tuples.append(new_tuple.copy())
            else:
                # Replace existing tuple
                self._tuples = [t for t in self._tuples if not (
                    t["user"] == key[0] and
                    t["relation"] == key[1] and 
                    t["object"] == key[2]
                )]
                self._tuples.append(new_tuple.copy())

    def delete(self, tuples: List[Dict[str, str]]):
        """Remove tuples from cache."""
        delete_keys = set((t["user"], t["relation"], t["object"]) for t in tuples)
        self._tuples = [t for t in self._tuples if not (
            (t["user"], t["relation"], t["object"]) in delete_keys
        )]

    def get_data(self) -> Dict[str, List[Dict[str, str]]]:
        """Get all cached tuples."""
        return {"tuples": self._tuples.copy()}

class OpenFGAClient(BasePolicyStoreClient):
    """OpenFGA client implementation"""

    def __init__(
        self,
        openfga_server_url=None,
        openfga_auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        store_id: Optional[str] = None,
        data_updater_enabled: bool = True,
        policy_updater_enabled: bool = True,
        cache_policy_data: bool = False,
    ):
        # Base initialization
        base_url = openfga_server_url or opal_client_config.POLICY_STORE_URL
        self._openfga_url = base_url.rstrip('/')
        self._store_id = store_id or opal_client_config.OPENFGA_STORE_ID
        self._base_url = f"{self._openfga_url}/stores/{self._store_id}"
        self._policy_version: Optional[str] = None
        self._token = openfga_auth_token
        self._auth_type: PolicyStoreAuth = auth_type
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

        # Initialize transaction logging
        self._transaction_state = OpenFGATransactionLogState(
            data_updater_enabled=data_updater_enabled,
            policy_updater_enabled=policy_updater_enabled,
        )

        self._transaction_state_writer = None

        # Initialize data cache if enabled
        self._policy_data_cache: Optional[OpenFGAStaticDataCache] = None
        if cache_policy_data:
            self._policy_data_cache = OpenFGAStaticDataCache()

        # Validate auth configuration  
        if auth_type == PolicyStoreAuth.OAUTH:
            raise ValueError("OpenFGA doesn't support OAuth authentication")
        if auth_type == PolicyStoreAuth.TOKEN and not openfga_auth_token:
            raise ValueError("Authentication token required when using TOKEN auth type")

        logger.info(f"Authentication mode for policy store: {auth_type}")

    async def setup(self):
        """Async setup that must be called after initialization."""
        self._transaction_state_writer = OpenFGATransactionLogPolicyWriter(
            policy_store=self,
            store_id=self._store_id
        )
        await self._transaction_state_writer.initialize()

        await self._transaction_state_writer.persist(self._transaction_state)


    async def init_healthcheck_policy(self, store_id: str):
        """Initialize the healthcheck policy tracking."""
        self._transaction_state_writer = OpenFGATransactionLogPolicyWriter(
            policy_store=self,
            store_id=store_id
        )
        await self._transaction_state_writer.initialize()
        return await self._transaction_state_writer.persist(self._transaction_state)

    # Add method to initialize if not already initialized
    async def _ensure_initialized(self):
        """Ensure client is properly initialized."""
        if self._transaction_state_writer is None:
            await self.setup()



    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an authenticated session."""
        if self._session is None or self._session.closed:
            headers = {"Content-Type": "application/json"}
            if self._auth_type == PolicyStoreAuth.TOKEN and self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ):
        """Write authorization model to OpenFGA."""
        start_time = datetime.utcnow().isoformat()
        try:
            policy = json.loads(policy_code)
            session = await self._get_session()

            async with session.post(
                f"{self._base_url}/authorization-models",
                json=policy
            ) as response:
                if response.status == 201:
                    data = await response.json()
                    self._policy_version = data["authorization_model_id"]
                    
                    # Create successful transaction
                    transaction = StoreTransaction(
                        id=transaction_id or str(uuid.uuid4()),
                        actions=["set_policy"],
                        transaction_type=TransactionType.policy,
                        success=True,
                        creation_time=start_time,
                        end_time=datetime.utcnow().isoformat()
                    )
                    
                    await self.log_transaction(transaction)
                    logger.info(f"Successfully set policy with model ID: {self._policy_version}")
                    return data
                else:
                    error_body = await response.text()
                    raise Exception(f"Failed to set policy: HTTP {response.status} - {error_body}")
                    
        except Exception as e:
            logger.error(f"Error setting policy: {str(e)}")
            
            # Create failed transaction
            transaction = StoreTransaction(
                id=transaction_id or str(uuid.uuid4()),
                actions=["set_policy"],
                transaction_type=TransactionType.policy,
                success=False,
                error=str(e),
                creation_time=start_time,
                end_time=datetime.utcnow().isoformat()
            )
            await self.log_transaction(transaction)
            raise
    


    async def _write_tuple(self, tuple_data: Dict[str, str]) -> bool:
        """Write a single tuple to OpenFGA.
        
        Args:
            tuple_data: Dict containing user, relation, and object
            
        Returns:
            bool: True if write was successful
            
        Raises:
            aiohttp.ClientError: For network/connection errors
            Exception: For other failures
        """
        try:
            session = await self._get_session()
            writes = {
                "writes": {
                    "tuple_keys": [{
                        "user": tuple_data["user"],
                        "relation": tuple_data["relation"],
                        "object": tuple_data["object"]
                    }]
                }
            }

            async with session.post(
                f"{self._base_url}/write",
                json=writes
            ) as response:
                if response.status == 200:
                    return True
                    
                # Handle duplicate tuple error gracefully 
                if response.status == 400:
                    error_data = await response.json()
                    if (error_data.get("code") == "write_failed_due_to_invalid_input" and
                        "already exists" in error_data.get("message", "")):
                        return True

                response.raise_for_status()
                return False
                
        except Exception as e:
            # Let client errors propagate
            if isinstance(e, aiohttp.ClientError):
                raise
            # Re-raise other errors
            raise Exception(f"Failed to write tuple: {str(e)}")
            
    @affects_transaction
    @retry(**RETRY_CONFIG) 
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ):
        """Set relationship tuples in OpenFGA."""
        start_time = datetime.utcnow().isoformat()
        try:
            # Transform data into tuples format
            if isinstance(policy_data, dict) and "tuples" in policy_data:
                tuples = policy_data["tuples"]
            elif isinstance(policy_data, list):
                tuples = policy_data
            else:
                raise ValueError(f"Invalid policy data format: {policy_data}")

            # Process tuples
            for tuple in tuples:
                await self._write_tuple(tuple)  # Let ClientError propagate

            # Create successful transaction
            transaction = StoreTransaction(
                id=transaction_id or str(uuid.uuid4()),
                actions=["set_policy_data"],
                transaction_type=TransactionType.data,
                success=True,
                creation_time=start_time,
                end_time=datetime.utcnow().isoformat()
            )
            await self.log_transaction(transaction)

        except aiohttp.ClientError:
            # Create failed transaction before re-raising
            transaction = StoreTransaction(
                id=transaction_id or str(uuid.uuid4()),
                actions=["set_policy_data"], 
                transaction_type=TransactionType.data,
                success=False,
                error="Network error occurred",
                creation_time=start_time,
                end_time=datetime.utcnow().isoformat()
            )
            await self.log_transaction(transaction)
            raise  # Re-raise original ClientError

        except Exception as e:
            logger.error(f"Error in set_policy_data: {str(e)}")
            raise
        
    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        """Get an authorization model by ID.
        
        Args:
            policy_id (str): The authorization model ID to retrieve
            
        Returns:
            Optional[str]: The authorization model as a JSON string, or None if not found/error
        """
        try:
            if not policy_id:
                logger.warning("Invalid empty policy_id provided")
                return None

            session = await self._get_session()
            async with session.get(
                f"{self._base_url}/authorization-models/{policy_id}",
                **self._get_request_args()
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "authorization_model" not in data:
                        logger.error(f"Invalid response format from OpenFGA - missing authorization_model key: {data}")
                        return None
                    
                    # Update policy version if this is the latest model
                    if self._is_latest_model(data["authorization_model"]):
                        self._policy_version = policy_id
                    
                    return json.dumps(data["authorization_model"])
                elif response.status == 404:
                    logger.info(f"Authorization model with ID {policy_id} not found")
                    return None
                else:
                    error_body = await response.text()
                    logger.error(
                        f"Failed to get authorization model {policy_id}: HTTP {response.status} - {error_body}"
                    )
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"Network error getting authorization model {policy_id}: {str(e)}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response for authorization model {policy_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting authorization model {policy_id}: {str(e)}")
            return None

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_policies(self) -> Optional[Dict[str, str]]:
        """Get all authorization models."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self._base_url}/authorization-models"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        model["id"]: json.dumps(model)
                        for model in data.get("authorization_models", [])
                    }
                return None
        except Exception as e:
            logger.error(f"Error in get_policies: {str(e)}")
            return None

    async def get_policy_module_ids(self) -> List[str]:
        """Get all authorization model IDs."""
        policies = await self.get_policies()
        return list(policies.keys()) if policies else []


    @affects_transaction  
    async def set_policies(
        self,
        bundle: PolicyBundle,
        transaction_id: Optional[str] = None
    ):
        """Set policies from a bundle."""
        async with self._lock:
            start_time = datetime.utcnow().isoformat()
            try:
                # Set new/updated policies
                for policy in bundle.policy_modules:
                    await self.set_policy(policy.path, policy.rego)
                
                # Handle deleted modules
                deleted_modules: Union[List[str], Set[str]] = []
                if bundle.old_hash is None:
                    # For complete bundle, remove policies that aren't in bundle
                    existing_modules = set(await self.get_policy_module_ids())
                    bundle_modules = set(policy.path for policy in bundle.policy_modules)
                    deleted_modules = existing_modules - bundle_modules
                elif bundle.deleted_files is not None:
                    # For delta bundle, only remove explicitly deleted modules
                    deleted_modules = [str(module) for module in bundle.deleted_files.policy_modules]

                # Log deletion attempts even though OpenFGA doesn't support deletion
                for module_id in deleted_modules:
                    logger.warning(f"Attempted to delete policy {module_id} - OpenFGA doesn't support policy deletion")

                self._policy_version = bundle.hash

                # Create successful transaction
                transaction = StoreTransaction(
                    id=transaction_id or str(uuid.uuid4()),
                    actions=["set_policies"],
                    transaction_type=TransactionType.policy,
                    success=True,
                    creation_time=start_time,
                    end_time=datetime.utcnow().isoformat()
                )
                await self.log_transaction(transaction)

            except Exception as e:
                logger.error(f"Error setting policies from bundle: {str(e)}")
                # Create failed transaction
                transaction = StoreTransaction(
                    id=transaction_id or str(uuid.uuid4()),
                    actions=["set_policies"],
                    transaction_type=TransactionType.policy,
                    success=False,
                    error=str(e),
                    creation_time=start_time,
                    end_time=datetime.utcnow().isoformat()
                )
                await self.log_transaction(transaction)
                raise

    async def delete_policy(self, policy_id: str, transaction_id: Optional[str] = None):
        """OpenFGA doesn't support deletion of authorization models."""
        logger.warning(f"Attempted to delete policy {policy_id} - OpenFGA doesn't support policy deletion")
        return None

    @fail_silently()
    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str = "") -> Dict:
        """Get relationship tuples, optionally filtered by path/object."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/read",
                json={"tuple_key": {"object": path} if path else {}}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "tuples": [
                            {
                                "user": tuple["key"]["user"],
                                "relation": tuple["key"]["relation"],
                                "object": tuple["key"]["object"]
                            }
                            for tuple in data.get("tuples", [])
                        ]
                    }
                return {}
        except Exception as e:
            logger.error(f"Error in get_data: {str(e)}")
            return {}

    @retry(**RETRY_CONFIG)
    async def get_data_with_input(self, path: str, input_model: Any) -> Dict:
        """Check authorization with context."""
        try:
            input_data = input_model.dict()
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/check",
                json={
                    "tuple_key": {
                        "user": input_data.get("user"),
                        "relation": input_data.get("relation"), 
                        "object": path
                    },
                    "authorization_model_id": self._policy_version,  # Add this
                    "context": input_data.get("context", {}),
                    "contextual_tuples": input_data.get("contextual_tuples", {"tuple_keys": []}),
                    "consistency": "MINIMIZE_LATENCY"  # Add consistency preference
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "allowed": data.get("allowed", False),
                        "resolution": data.get("resolution")
                    }
                return {"allowed": False}
        except Exception as e:
            logger.error(f"Error in get_data_with_input: {str(e)}")
            return {"allowed": False}


    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self,
        path: str = "",
        transaction_id: Optional[str] = None
    ):
        """Delete relationship tuples in OpenFGA."""
        start_time = datetime.utcnow().isoformat()
        try:
            # First get existing tuples
            existing_tuples = await self.get_data(path)
            if not existing_tuples.get("tuples"):
                return

            # Delete tuples by writing empty set
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/write",
                json={
                    "deletes": {
                        "tuple_keys": [
                            {
                                "user": tuple["user"],
                                "relation": tuple["relation"],
                                "object": tuple["object"]
                            }
                            for tuple in existing_tuples["tuples"]
                        ]
                    }
                }
            ) as response:
                if response.status == 200:
                    if self._policy_data_cache:
                        self._policy_data_cache.delete(existing_tuples["tuples"])

                    # Create successful transaction
                    transaction = StoreTransaction(
                        id=transaction_id or str(uuid.uuid4()),
                        actions=["delete_policy_data"],
                        transaction_type=TransactionType.data,
                        success=True,
                        creation_time=start_time,
                        end_time=datetime.utcnow().isoformat()
                    )
                    await self.log_transaction(transaction)
                else:
                    error_body = await response.text()
                    raise Exception(f"Failed to delete policy data: {error_body}")

        except Exception as e:
            logger.error(f"Error in delete_policy_data: {str(e)}")
            # Create failed transaction
            transaction = StoreTransaction(
                id=transaction_id or str(uuid.uuid4()),
                actions=["delete_policy_data"],
                transaction_type=TransactionType.data,
                success=False,
                error=str(e),
                creation_time=start_time,
                end_time=datetime.utcnow().isoformat()
            )
            await self.log_transaction(transaction)
            raise
    

    def _get_request_args(self) -> Dict[str, Any]:
        """Get common request arguments including any custom headers."""
        args = {}
        if hasattr(self, "_ssl_context_kwargs"):
            args.update(self._ssl_context_kwargs)
        return args

    def _is_latest_model(self, model: Dict[str, Any]) -> bool:
        """Check if this authorization model is the latest version.
        
        Args:
            model (Dict[str, Any]): The authorization model response
            
        Returns:
            bool: True if this appears to be the latest model version
        """
        try:
            # Could add additional checks here based on timestamps or version numbers
            # For now just validate the model appears valid
            return all(key in model for key in ("id", "schema_version", "type_definitions"))
        except Exception:
            return False


    async def log_transaction(self, transaction: StoreTransaction):
        """Process and log a transaction, updating state."""
        try:
            # Update state
            self._transaction_state.process_transaction(transaction)
            
            # Persist if we have a writer
            if self._transaction_state_writer:
                await self._transaction_state_writer.persist(self._transaction_state)
            
            # Log transaction details
            success_str = "succeeded" if transaction.success else "failed"
            action_str = ", ".join(transaction.actions) if transaction.actions else "unknown action"
            transaction_type = transaction.transaction_type.value if transaction.transaction_type else "unknown type"
            
            log_msg = f"OpenFGA transaction {success_str} - Type: {transaction_type}, Actions: {action_str}"
            if transaction.success:
                logger.info(log_msg)
            else:
                error_msg = f"{log_msg}, Error: {transaction.error}" if transaction.error else log_msg
                logger.error(error_msg)
                
        except Exception as e:
            logger.error(f"Error logging transaction: {str(e)}")

    async def is_ready(self) -> bool:
        """Check if OpenFGA client is ready to handle requests."""
        return self._transaction_state.ready

    async def is_healthy(self) -> bool:
        """Check overall health of OpenFGA client."""
        return self._transaction_state.healthy

    async def get_policy_version(self) -> Optional[str]:
        """Get current authorization model ID."""
        return self._policy_version


    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        """Export full state to a file."""
        policies = await self.get_policies()
        if self._policy_data_cache:
            data = self._policy_data_cache.get_data()
        else:
            data = await self.get_data()
        
        await writer.write(
            json.dumps({"policies": policies, "data": data}, default=str)
        )

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        """Import full state from a file."""
        import_data = json.loads(await reader.read())
        
        # Import policies
        for policy_id, policy_code in import_data.get("policies", {}).items():
            await self.set_policy(policy_id, policy_code)
            
        # Import data
        if "data" in import_data:
            await self.set_policy_data(import_data["data"])