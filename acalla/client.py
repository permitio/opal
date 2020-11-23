import acalla
import requests
import json

from typing import Optional, List, Callable, Dict, Any

from .enforcer import enforcer_factory
from .constants import POLICY_SERVICE_URL, UPDATE_INTERVAL_IN_SEC
from .resource_registry import resource_registry, ResourceDefinition, ActionDefinition

class ResourceStub:
    def __init__(self, resource_name: str):
        self._resource_name = resource_name

    def action(
        self,
        name: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        path: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        attributes = attributes or {}
        attributes.update(kwargs)
        action = ActionDefinition(
            name=name,
            title=title,
            description=description,
            path=path,
            attributes=attributes
        )
        authorization_client.add_action_to_resource(self._resource_name, action)


class AuthorizationClient:
    def __init__(self):
        self._initialized = False
        self._registry = resource_registry

    def initialize(self, token, app_name, service_name, **kwargs):
        self._token = token
        self._client_context = {"app_name": app_name, "service_name": service_name}
        self._client_context.update(kwargs)
        self._initialized = True
        self._requests = requests.session()
        self._requests.headers.update(
            {"Authorization": "Bearer {}".format(self._token)}
        )
        self._sync_resources()

    def fetch_policy(self):
        """
        get rego
        """
        self._throw_if_not_initialized()
        response = self._requests.get(f"{POLICY_SERVICE_URL}/policy")
        return response.text

    def fetch_policy_data(self):
        """
        get opa data.json
        """
        self._throw_if_not_initialized()
        response = self._requests.get(f"{POLICY_SERVICE_URL}/policy-config")
        return response.json()

    def add_resource(self, resource: ResourceDefinition) -> ResourceStub:
        self._registry.add_resource(resource)
        self._maybe_sync_resource(resource)
        return ResourceStub(resource.name)

    def add_action_to_resource(self, resource_name: str, action: ActionDefinition):
        action = self._registry.add_action_to_resource(resource_name, action)
        if action is not None:
            self._maybe_sync_action(action)

    def _maybe_sync_resource(self, resource: ResourceDefinition):
        if self._initialized and not self._registry.is_synced(resource):
            print("syncing resource: {}".format(resource))
            response = self._requests.put(
                f"{POLICY_SERVICE_URL}/resource",
                data=json.dumps(resource.dict()),
            )
            self._registry.mark_as_synced(
                resource, remote_id=response.json().get('id'))

    def _maybe_sync_action(self, action: ActionDefinition):
        resource_id = action.resource_id
        if resource_id is None:
            return

        if self._initialized and not self._registry.is_synced(action):
            print("syncing action: {}".format(action))
            response = self._requests.put(
                f"{POLICY_SERVICE_URL}/resource/{resource_id}/action",
                data=json.dumps(action.dict())
            )
            self._registry.mark_as_synced(
                action, remote_id=response.json().get('id'))

    def _sync_resources(self):
        # will also sync actions
        for resource in self._registry.resources:
            self._maybe_sync_resource(resource)

    def sync_user(
        self,
        user_id: str,
        user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        self._throw_if_not_initialized()
        data = {
            "id": user_id,
            "data": user_data
        }
        response = self._requests.put(
            f"{POLICY_SERVICE_URL}/user",
            data=json.dumps(data),
        )
        return response.json()

    def sync_org(
        self,
        org_id: str,
        org_name: str,
        org_metadata: Dict[str, Any]={}
    ):
        self._throw_if_not_initialized()
        data = {
            "external_id": org_id,
            "name": org_name,
        }
        response = self._requests.post(
            f"{POLICY_SERVICE_URL}/organization",
            data=json.dumps(data),
        )
        return response.json()

    def delete_org(
        self,
        org_id: str
    ):
        self._throw_if_not_initialized()
        self._requests.delete(
            f"{POLICY_SERVICE_URL}/organization/{org_id}",
        )

    def add_user_to_org(
        self,
        user_id: str,
        org_id: str
    ):
        self._throw_if_not_initialized()
        data = {
            "user_id": user_id,
            "org_id": org_id,
        }
        response = self._requests.post(
            f"{POLICY_SERVICE_URL}/add_user_to_org",
            data=json.dumps(data),
        )
        return response.json()

    def get_orgs_for_user(
        self,
        user_id: str
    ):
        self._throw_if_not_initialized()
        response = self._requests.get(
            f"{POLICY_SERVICE_URL}/get_orgs_for_user/{user_id}",
        )
        return response.json()

    def assign_role(
        self,
        role: str,
        user_id: str,
        org_id: str
    ):
        self._throw_if_not_initialized()
        data = {
            "role": role,
            "user_id": user_id,
            "org_id": org_id,
        }
        response = self._requests.post(
            f"{POLICY_SERVICE_URL}/assign_role",
            data=json.dumps(data),
        )
        return response.json()

    def _throw_if_not_initialized(self):
        if not self._initialized:
            raise RuntimeError("You must call acalla.init() first!")


authorization_client = AuthorizationClient()
