package security.validation.user.validate.utils.policy_0969

# Auto-generated policy 969 (Rego v1 syntax)
# Package: security.validation.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0969",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0969_allowed if {
    input.user.active
    input.resource.public
}
default policy_0969_allowed = false
policy_0969_allowed if {
    data.policies.security.enabled
}
policy_0969_allowed if {
    input.user.role == "admin"
}
