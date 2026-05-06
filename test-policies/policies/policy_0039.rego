package security.monitoring.context.allow.utils.policy_0039

# Auto-generated policy 39 (Rego v1 syntax)
# Package: security.monitoring.context.allow.utils

# Metadata
metadata := {
    "policy_id": "0039",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0039_allowed if {
    input.user.role == "admin"
}
default policy_0039_allowed = false
