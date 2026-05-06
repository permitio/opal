package security.enforcement.policy.validate.policy_0077

# Auto-generated policy 77 (Rego v1 syntax)
# Package: security.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0077",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0077_allowed = false
policy_0077_allowed if {
    data.policies.security.enabled
}
policy_0077_allowed if {
    input.user.role == "admin"
}
