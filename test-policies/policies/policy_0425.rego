package audit.monitoring.action.allow.utils.policy_0425

# Auto-generated policy 425 (Rego v1 syntax)
# Package: audit.monitoring.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0425",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0425_allowed = false
policy_0425_allowed if {
    input.user.active
    input.resource.public
}
