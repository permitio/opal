package audit.validation.resource.validate.logic.policy_0485

# Auto-generated policy 485 (Rego v1 syntax)
# Package: audit.validation.resource.validate.logic

# Metadata
metadata := {
    "policy_id": "0485",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0485_allowed if {
    input.user.active
    input.resource.public
}
default policy_0485_allowed = false
