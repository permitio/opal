package security.validation.policy.allow.utils.policy_0047

# Auto-generated policy 47 (Rego v1 syntax)
# Package: security.validation.policy.allow.utils

# Metadata
metadata := {
    "policy_id": "0047",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0047_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0047_allowed if {
    input.user.role == "admin"
}
