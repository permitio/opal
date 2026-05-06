package access.validation.policy.check.core.policy_0036

# Auto-generated policy 36 (Rego v1 syntax)
# Package: access.validation.policy.check.core

# Metadata
metadata := {
    "policy_id": "0036",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0036_allowed = false
policy_0036_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
