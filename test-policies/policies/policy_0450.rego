package security.validation.user.validate.helpers.policy_0450

# Auto-generated policy 450 (Rego v1 syntax)
# Package: security.validation.user.validate.helpers

# Metadata
metadata := {
    "policy_id": "0450",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0450_allowed if {
    input.user.active
    input.resource.public
}
default policy_0450_allowed = false
policy_0450_allowed if {
    input.user.role == "admin"
}
