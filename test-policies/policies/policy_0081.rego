package security.enforcement.policy.allow.policy_0081

# Auto-generated policy 81 (Rego v1 syntax)
# Package: security.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0081",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0081_allowed if {
    input.user.active
    input.resource.public
}
default policy_0081_allowed = false
policy_0081_allowed if {
    data.policies.security.enabled
}
