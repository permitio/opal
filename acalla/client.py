import time
import acalla
import requests
import threading

from typing import Optional, List, Callable, Dict, Any

from .enforcer import enforcer_factory
from .constants import POLICY_SERVICE_URL, UPDATE_INTERVAL_IN_SEC


class ResourceStub:
    def __init__(self, remote_id: str):
        self._remote_id = remote_id

    @classmethod
    def from_response(cls, json):
        return ResourceStub(json.get('id'))

    def action(
        self,
        name: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        path: Optional[str] = None,
        **attributes
    ):
        if self._remote_id is None:
            return

        return acalla.action(
            name=name,
            title=title,
            description=description,
            path=path,
            resource_id=self._remote_id
            **attributes
        )


class AuthorizationClient:
    def __init__(self):
        self._initialized = False

    def initialize(self, token, app_name, service_name, **kwargs):
        self._token = token
        self._client_context = {"app_name": app_name, "service_name": service_name}
        self._client_context.update(kwargs)
        self._initialized = True
        self._requests = requests.session()
        self._requests.headers.update(
            {"Authorization": "Bearer {}".format(self._token)}
        )

    def resource(
        self,
        *,
        name: str,
        type: str,
        path: str,
        description: str = None,
        actions: Optional[List[Dict[str, Any]]],
    ) -> ResourceStub:
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
        actions = actions or []
        response = self._requests.put(
            f"{POLICY_SERVICE_URL}/resource",
            data={
                "name": name,
                "type": type,
                "path": path,
                "description": description,
                "actions": [a for a in actions if a],
            },
        )
        return ResourceStub.from_response(response.json())

    def action(
            self,
            name: str,
            title: Optional[str] = None,
            description: Optional[str] = None,
            path: Optional[str] = None,
            resource_id: Optional[str] = None,
            **attributes
        ) -> Dict[str, Any]:
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
        action_data = {
            "name": name,
            "title": title,
            "description": description,
            "path": path,
            "attributes": attributes
        }
        if resource_id is not None:
            self._requests.put(
                f"{POLICY_SERVICE_URL}/resource/{resource_id}/action",
                data=action_data
            )
            return {}
        else:
            return action_data

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


class PolicyUpdater:
    def __init__(self, update_interval=UPDATE_INTERVAL_IN_SEC):
        self.set_interval(update_interval)
        self._thread = threading.Thread(target=self._run, args=())
        self._thread.daemon = True

    def set_interval(self, update_interval):
        self._interval = update_interval

    def on_interval(self, callback: Callable):
        self._callback = callback

    def start(self):
        if self._interval is not None:
            self._thread.start()

    def _run(self):
        while True:
            time.sleep(self._interval)
            self._callback()


policy_updater = PolicyUpdater()


def update_policy():
    policy = authorization_client.fetch_policy()
    enforcer_factory.set_policy(policy)


def update_policy_data():
    policy_data = authorization_client.fetch_policy_data()
    enforcer_factory.set_policy_data(policy_data)


def init(token, app_name, service_name, **kwargs):
    """
    inits the acalla client
    """
    authorization_client.initialize(
        token=token, app_name=app_name, service_name=service_name, **kwargs
    )

    if "update_interval" in kwargs:
        policy_updater.set_interval(kwargs.get("update_interval"))

    # initial fetch of policy
    update_policy()
    update_policy_data()

    # fetch and update policy every {interval} seconds
    policy_updater.on_interval(update_policy_data)
    policy_updater.start()