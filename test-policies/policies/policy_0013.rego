package security.enforcement.action.verify.policy_0013

# Auto-generated policy 13 (Rego v1 syntax)
# Package: security.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0013",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0013_allowed if {
    data.policies.security.enabled
}
policy_0013_allowed if {
    input.user.role == "admin"
}
default policy_0013_allowed = false
