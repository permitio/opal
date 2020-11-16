import acalla
import requests
import json

from typing import Optional, List, Callable, Dict, Any

from .enforcer import enforcer_factory
from .constants import POLICY_SERVICE_URL, UPDATE_INTERVAL_IN_SEC
from .resource_registry import ResourceRegistry, ResourceDefinition, ActionDefinition


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
        self._registry = ResourceRegistry()

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

    def new_user(self):
        """
        sync the user to authz service

        usage:
        acalla.new_user(id=user_id, data=user_data)
        """
        self._throw_if_not_initialized()
        print("acalla.new_user()")

    def new_resource(self):
        """
        call this on resource creation, syncs the resource to authz service.

        usage:
        acalla.new_resource(id=<resource id>, name=<resource name>)
        acalla.new_resource(id=<resource id>, path=<resource path>)
        """
        self._throw_if_not_initialized()
        print("acalla.new_resource()")

    def remove_resource(self):
        """
        call this on resource destruction
        """
        self._throw_if_not_initialized()
        print("acalla.new_resource()")

    def fetch_policy(self):
        """
        get rego
        """
        response = self._requests.get(f"{POLICY_SERVICE_URL}/policy")
        return response.text

    def fetch_policy_data(self):
        """
        get opa data.json
        """
        response = self._requests.get(f"{POLICY_SERVICE_URL}/policy-config")
        return response.json()

    def _throw_if_not_initialized(self):
        if not self._initialized:
            raise RuntimeError("You must call acalla.init() first!")


authorization_client = AuthorizationClient()
