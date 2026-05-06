package security.authentication.policy.deny.policy_0914

# Auto-generated policy 914 (Rego v1 syntax)
# Package: security.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0914",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0914_allowed if {
    input.user.role == "admin"
}
default policy_0914_allowed = false
policy_0914_allowed if {
    data.policies.security.enabled
}
