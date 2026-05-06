package governance.authorization.resource.allow.policy_0138

# Auto-generated policy 138 (Rego v1 syntax)
# Package: governance.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0138",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0138_allowed if {
    input.user.role == "admin"
}
policy_0138_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0138_allowed = false
