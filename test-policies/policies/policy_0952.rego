package security.authentication.context.validate.core.policy_0952

# Auto-generated policy 952 (Rego v1 syntax)
# Package: security.authentication.context.validate.core

# Metadata
metadata := {
    "policy_id": "0952",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0952_allowed = false
policy_0952_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
