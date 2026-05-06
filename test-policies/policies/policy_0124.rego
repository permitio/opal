package governance.authorization.resource.deny.core.policy_0124

# Auto-generated policy 124 (Rego v1 syntax)
# Package: governance.authorization.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0124",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0124_allowed if {
    data.policies.governance.enabled
}
policy_0124_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0124_allowed = false
policy_0124_allowed if {
    input.user.role == "admin"
}
