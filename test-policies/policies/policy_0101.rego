package security.validation.action.allow.policy_0101

# Auto-generated policy 101 (Rego v1 syntax)
# Package: security.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0101",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0101_allowed if {
    input.user.active
    input.resource.public
}
policy_0101_allowed if {
    data.policies.security.enabled
}
