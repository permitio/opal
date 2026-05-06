package security.authorization.resource.validate.logic.policy_0924

# Auto-generated policy 924 (Rego v1 syntax)
# Package: security.authorization.resource.validate.logic

# Metadata
metadata := {
    "policy_id": "0924",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0924_allowed = false
policy_0924_allowed if {
    input.user.active
    input.resource.public
}
