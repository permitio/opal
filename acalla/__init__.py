from .client import init, authorization_client as _authorization_client, policy_updater as _updater
from .enforcer import enforcer_factory as _enforcer_factory
from .markers import resource_id, resource_type, org_id

resource = _authorization_client.resource
action = _authorization_client.action
new_user = _authorization_client.new_user
new_resource = _authorization_client.new_resource

set_user = _enforcer_factory.set_user
set_org = _enforcer_factory.set_org
set_context = _enforcer_factory.set_context
is_allowed = _enforcer_factory.is_allowed
set_policy_update_interval = _updater.set_interval

__all__ = [
    'init',
    'resource',
    'action',
    'new_user',
    'new_resource',
    'set_user',
    'set_org',
    'set_context',
    'is_allowed',
    'resource_id',
    'resource_type',
    'org_id',
    'set_policy_update_interval',
]