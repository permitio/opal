from typing import Optional, List, Callable, Dict, Any, Union


class ActionDefinition:
    def __init__(
        self,
        name: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        path: Optional[str] = None,
        resource_id: Optional[str] = None,
        attributes: Dict[str, Any] = {}
    ):
        self.name = name
        self.title = title
        self.description = description
        self.path = path
        self.attributes = attributes
        self._resource_id = resource_id
        self._resource_name = None

    @property
    def resource_id(self) -> str:
        return self._resource_id

    @property
    def resource_name(self) -> str:
        return self._resource_name

    def set_resource_id(self, resource_id: str):
        self._resource_id = resource_id

    def set_resource_name(self, resource_name: str):
        self._resource_name = resource_name

    def dict(self):
        d = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "path": self.path,
            "attributes": self.attributes,
        }
        if self._resource_id is not None:
            d["resource_id"] = self._resource_id
        return d

    def __repr__(self):
        return "ActionDefinition(name='{}', path='{}')".format(self.name, self.path)


class ResourceDefinition:
    def __init__(
        self,
        name: str,
        type: str,
        path: str,
        description: str = None,
        actions: List[ActionDefinition] = [],
        attributes: Dict[str, Any] = {}
    ):
        self.name = name
        self.type = type
        self.path = path
        self.description = description
        self.actions = actions
        self.attributes = attributes
        self._remote_id = None

    @property
    def remote_id(self) -> str:
        return self._remote_id

    def set_remote_id(self, remote_id: str):
        self._remote_id = remote_id

    def dict(self):
        return {
            "name": self.name,
            "type": self.type,
            "path": self.path,
            "description": self.description,
            "actions": [a.dict() for a in self.actions],
            "attributes": self.attributes,
        }

    def __repr__(self):
        return "ResourceDefinition(name='{}', path='{}', actions={})".format(
            self.name,
            self.path,
            repr(self.actions)
        )


class ResourceRegistry:
    def __init__(self):
        self._resources = {}
        self._already_synced = set()

    @property
    def resources(self):
        return self._resources.values()

    def add_resource(self, resource: ResourceDefinition):
        if not resource.name in self._resources:
            self._resources[resource.name] = resource

        for action in resource.actions:
            action.set_resource_name(resource.name)

    def add_action_to_resource(
        self, resource_name: str, action: ActionDefinition
    ) -> Optional[ActionDefinition]:
        if not resource_name in self._resources:
            return None

        resource = self._resources[resource_name]
        action.set_resource_id(resource.remote_id)
        action.set_resource_name(resource.name)

        existing_actions = [action.name for action in resource.actions]
        if not action.name in existing_actions:
            resource.actions.append(action)
        return action

    def is_synced(self, obj: Union[ResourceDefinition, ActionDefinition]) -> bool:
        if isinstance(obj, ResourceDefinition):
            return obj.name in self._already_synced

        if isinstance(obj, ActionDefinition):
            return self.action_key(obj) in self._already_synced

        return False

    def mark_as_synced(
        self, obj: Union[ResourceDefinition, ActionDefinition], remote_id: str
    ):
        if isinstance(obj, ResourceDefinition):
            self._already_synced.add(obj.name)
            self._resources[obj.name].set_remote_id(remote_id)
            for action in obj.actions:
                self._already_synced.add(self.action_key(action))

        if isinstance(obj, ActionDefinition):
            self._already_synced.add(self.action_key(obj))

    @classmethod
    def action_key(cls, action: ActionDefinition) -> str:
        return "{}:{}".format(action.resource_name, action.name)
