from functools import wraps
from typing import Callable

class AuthorizationMarkers:
    def __init__(self):
        self._registry = {}

    def register_method(self, cls_name, method_name, authz_alias):
        self._registry.setdefault(cls_name, {})[authz_alias] = method_name

    @property
    def registry(self):
        return self._registry

authorization_markers = AuthorizationMarkers()

def mark(marker: str) -> Callable:
    """
    this decorator allows us to mark methods on inspected resource objects,
    so that we can later evaluate the correct properties for enforcement.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(self, *args, **kwargs):
            authorization_markers.register_method(self.__class__.__name__, f.__name__, marker)
            return f(self, *args, **kwargs)
        return wrapper
    return decorator

resource_id = mark('resource_id')
resource_type = mark('resource_type')
org_id = mark('org_id')