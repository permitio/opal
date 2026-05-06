package access.enforcement.resource.deny.core.policy_0864

# Auto-generated policy 864 (Rego v1 syntax)
# Package: access.enforcement.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0864",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0864_allowed if {
    input.user.role == "admin"
}
default policy_0864_allowed = false
policy_0864_allowed if {
    data.policies.access.enabled
}
policy_0864_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
