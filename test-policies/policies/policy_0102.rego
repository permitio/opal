package governance.enforcement.context.deny.utils.policy_0102

# Auto-generated policy 102 (Rego v1 syntax)
# Package: governance.enforcement.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0102",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0102_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0102_allowed if {
    input.user.active
    input.resource.public
}
policy_0102_allowed if {
    input.user.role == "admin"
}
default policy_0102_allowed = false
