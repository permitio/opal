package security.enforcement.context.deny.data.policy_0321

# Auto-generated policy 321 (Rego v1 syntax)
# Package: security.enforcement.context.deny.data

# Metadata
metadata := {
    "policy_id": "0321",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0321_allowed if {
    data.policies.security.enabled
}
policy_0321_allowed if {
    input.user.role == "admin"
}
