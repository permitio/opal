import acalla
import requests

from typing import Optional, List

from .enforcer import enforcer_factory
from .constants import POLICY_SERVICE_URL

class UnboundAction:
    def dict(self):
        pass

class ResourceStub:
    @classmethod
    def from_response(cls, json):
        return ResourceStub()

class AuthorizationClient:
    def __init__(self):
        self._initialized = False

    def initialize(
        self,
        token,
        app_name,
        service_name,
        **kwargs
    ):
        self._token = token
        self._client_context = {
            "app_name": app_name,
            "service_name": service_name
        }
        self._client_context.update(kwargs)
        self._initialized = True
        self._requests = requests.session()
        self._requests.headers.update({"Authorization": "Bearer {}".format(self._token)})

    def resource(self, *, name: str, type: str, path: str, description: str = None, actions: Optional[List[UnboundAction]]) -> ResourceStub:
        """
        declare a resource type.

        usage:

        acalla.resource(
            name="Todo",
            description="todo item",
            type=acalla.types.REST,
            path="/lists/{list_id}/todos/{todo_id}",
            actions=[
                acalla.action(
                    name="add",
                    title="Add",
                    path="/lists/{list_id}/todos/",
                    verb="post", # acalla.types.http.POST
                ),
                ...
            ]
        )
        """
        self._throw_if_not_initialized()
        response = self._requests.put(f"{POLICY_SERVICE_URL}/resource", data = {
            "name": name,
            "type": type,
            "path": path,
            "description": description,
            "actions": [a.dict() for a in actions]
        })
        return ResourceStub.from_response(response.json())

    def action(self):
        """
        declare an action on a resource.

        usage:
        todo = acalla.resource( ... )
        todo.action(
            name="add",
            title="Add",
            path="/lists/{list_id}/todos/",
            verb="post", # acalla.types.http.POST
        )

        or inline inside acalla.resource(), like so:
        acalla.resource(
            ...,
            actions = [
                acalla.action(...),
                acalla.action(...),
            ]
        )
        """
        self._throw_if_not_initialized()
        print("acalla.action()")

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

def init(
    token,
    app_name,
    service_name,
    **kwargs
):
    """
    inits the acalla client
    """
    authorization_client.initialize(
        token=token,
        app_name=app_name,
        service_name=service_name,
        **kwargs
    )
    policy = authorization_client.fetch_policy()
    policy_data = authorization_client.fetch_policy_data()
    enforcer_factory.set_policy(policy)
    enforcer_factory.set_policy_data(policy_data)
