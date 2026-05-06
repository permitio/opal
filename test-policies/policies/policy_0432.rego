package security.validation.user.deny.core.policy_0432

# Auto-generated policy 432 (Rego v1 syntax)
# Package: security.validation.user.deny.core

# Metadata
metadata := {
    "policy_id": "0432",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0432_allowed if {
    input.user.active
    input.resource.public
}
policy_0432_allowed if {
    data.policies.security.enabled
}
