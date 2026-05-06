package audit.validation.user.allow.core.policy_0086

# Auto-generated policy 86 (Rego v1 syntax)
# Package: audit.validation.user.allow.core

# Metadata
metadata := {
    "policy_id": "0086",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0086_allowed = false
policy_0086_allowed if {
    input.user.active
    input.resource.public
}
