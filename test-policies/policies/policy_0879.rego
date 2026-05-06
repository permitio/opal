package security.authentication.action.check.policy_0879

# Auto-generated policy 879 (Rego v1 syntax)
# Package: security.authentication.action.check

# Metadata
metadata := {
    "policy_id": "0879",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0879_allowed if {
    data.policies.security.enabled
}
default policy_0879_allowed = false
