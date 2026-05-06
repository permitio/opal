package security.validation.context.allow.core.policy_0189

# Auto-generated policy 189 (Rego v1 syntax)
# Package: security.validation.context.allow.core

# Metadata
metadata := {
    "policy_id": "0189",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0189_allowed = false
policy_0189_allowed if {
    input.user.role == "admin"
}
