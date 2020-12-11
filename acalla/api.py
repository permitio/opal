from typing import Optional, List, Callable, Dict, Any

from .client import authorization_client, ResourceStub
from .resource_registry import ResourceDefinition, ActionDefinition
from .updater import policy_updater, update_policy, update_policy_data
from .enforcer import enforcer_factory
from .markers import resource_id, resource_type, org_id
from .constants import POLICY_SERVICE_URL, OPA_SERVICE_URL

def init(token, app_name, service_name, client_id, **kwargs):
    """
    inits the acalla client
    """
    print(f"acalla.init(backend_url={POLICY_SERVICE_URL}, opa_url={OPA_SERVICE_URL})")
    authorization_client.initialize(
        token=token, app_name=app_name, service_name=service_name, **kwargs
    )

    # initial fetch of policy
    update_policy()
    update_policy_data()

    policy_updater.set_client_id(client_id)
    policy_updater.start()

def resource(
    name: str,
    type: str,
    path: str,
    description: str = None,
    actions: List[ActionDefinition] = [],
    attributes: Optional[Dict[str, Any]] = None,
    **kwargs
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

    you can later add actions on that resource:

    todo = acalla.resource( ... )
    todo.action(
        name="add",
        title="Add",
        path="/lists/{list_id}/todos/",
        verb="post", # acalla.types.http.POST
    )
    """
    attributes = attributes or {}
    attributes.update(kwargs)
    resource = ResourceDefinition(
        name=name,
        type=type,
        path=path,
        description=description,
        actions=actions,
        attributes=attributes
    )
    return authorization_client.add_resource(resource)

def action(
        name: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        path: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ActionDefinition:
    """
    declare an action on a resource.

    usage:
    acalla.resource(
        ...,
        actions = [
            acalla.action(...),
            acalla.action(...),
        ]
    )
    """
    attributes = attributes or {}
    attributes.update(kwargs)
    return ActionDefinition(
        name=name,
        title=title,
        description=description,
        path=path,
        attributes=attributes
    )

sync_user = authorization_client.sync_user
sync_org = authorization_client.sync_org
delete_org = authorization_client.delete_org
add_user_to_org = authorization_client.add_user_to_org
get_orgs_for_user = authorization_client.get_orgs_for_user
assign_role = authorization_client.assign_role

set_user = enforcer_factory.set_user
set_org = enforcer_factory.set_org
set_context = enforcer_factory.set_context
is_allowed = enforcer_factory.is_allowed
transform_resource_context = enforcer_factory.add_transform
update_policy_data = update_policy_data