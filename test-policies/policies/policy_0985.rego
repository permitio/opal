package risk.validation.context.validate.core.policy_0985

# Auto-generated policy 985 (Rego v1 syntax)
# Package: risk.validation.context.validate.core

# Metadata
metadata := {
    "policy_id": "0985",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0985_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0985_allowed = false
