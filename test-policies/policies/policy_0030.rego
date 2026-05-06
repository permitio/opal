package security.validation.policy.deny.policy_0030

# Auto-generated policy 30 (Rego v1 syntax)
# Package: security.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0030",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0030_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0030_allowed if {
    data.policies.security.enabled
}
policy_0030_allowed if {
    input.user.role == "admin"
}
