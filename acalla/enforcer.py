import requests
import json
import copy

from pprint import pprint

from typing import Optional, Dict, Any, Callable

from .constants import JWT_USER_CLAIMS, OPA_SERVICE_URL
from .resource import Resource

def set_if_not_none(d: dict, k: str, v):
    if v is not None:
        d[k] = v

Context = Dict[str, str]
ContextTransform = Callable[[Context], Context]

class EnforcerFactory:
    POLICY_NAME = "rbac"

    def __init__(self):
        self._policy = None
        self._policy_data = {}
        self._context = {}
        self._transforms = []
        self._active_enforcer = Enforcer(self._context)

    def set_policy(self, policy):
        self._policy = policy
        requests.put(f"{OPA_SERVICE_URL}/policies/{self.POLICY_NAME}", data=policy, headers={'content-type': 'text/plain'})

    def set_policy_data(self, policy_data):
        self._policy_data = policy_data
        requests.put(f"{OPA_SERVICE_URL}/data", data=json.dumps(self._policy_data))

    def set_user(self, *, id: str = None, data: Optional[Dict[str, Any]] = None, from_jwt: Optional[Dict[str, Any]] = None):
        """
        sets the default user for the current authz context.

        usage:
        acalla.set_user(id="83db95ce954f41078d4e04dda95e8e40")
        acalla.set_user(id="83db95ce954f41078d4e04dda95e8e40", data={ ... })
        acalla.set_user(from_jwt=jwt_payload) # (called *after* you verified the jwt, payload is a dict with claims)
        """
        user_context = {}

        if id is not None:
            user_context["id"] = id

        if data is not None:
            user_context["user_data"] = data

        if from_jwt is not None:
            set_if_not_none(user_context, "id", from_jwt.get("sub", None))

            user_data_from_jwt = {}
            for claim in JWT_USER_CLAIMS:
                set_if_not_none(user_data_from_jwt, claim, from_jwt.get(claim, None))
            user_context["user_data"].update(user_data_from_jwt)

        self.set_context({"__user": user_context})

    def set_org(self, id: str):
        """
        sets the org for the current context.
        useful when syncing created objects (to associate them with an authz org).

        usage: acalla.set_org(id="<MY_CUSTOMER_ID>")
        """
        self.set_context({"__org_id": id})

    def set_context(self, context: Context):
        """
        TODO: enforcer per authz context
        """
        self._context.update(context)
        self._active_enforcer = Enforcer(self._context)

    def add_transform(self, transform: ContextTransform):
        self._transforms.append(transform)

    def _transform_context(self, initial_context: Context) -> Context:
        context = copy.deepcopy(initial_context)
        for transform in self._transforms:
            context = transform(context)
        return context

    def is_allowed(self, user, action, resource):
        """
        usage:

        acalla.is_allowed(user, 'get', '/tasks/23')
        acalla.is_allowed(user, 'get', '/tasks')


        acalla.is_allowed(user, 'post', '/lists/3/todos/37', context={org_id=2})


        acalla.is_allowed(user, 'view', task)
        acalla.is_allowed('view', task)

        TODO: create comprehesive input
        TODO: currently assuming resource is a dict
        """
        resource_dict = {}
        if isinstance(resource, str):
            resource_dict = Resource.from_path(resource).dict()
        elif isinstance(resource, Resource):
            resource_dict = resource.dict()
        elif isinstance(resource, dict):
            resource_dict = resource
        else:
            raise ValueError("Unsupported resource type: {}".format(type(resource)))

        resource_type = resource_dict["type"]
        print(f"acalla.is_allowed({user}, {resource_type}:{action})")

        resource_dict['context'] = self._transform_context(resource_dict['context'])
        opa_input = {
            "input": {
                "user": user,
                "action": action,
                "resource": resource_dict
            }
        }
        response = requests.post(f"{OPA_SERVICE_URL}/data/rbac/allow", data=json.dumps(opa_input))
        response_data = response.json()
        return response_data.get("result", False)

class Enforcer:
    def __init__(self, enforcer_context: Context):
        self._context = enforcer_context

    def is_allowed(self, user, action, resource):
        pass

enforcer_factory = EnforcerFactory()

# # dynamic properties
# ResourcePath()
# Resource()