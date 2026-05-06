package security.authentication.policy.deny.utils.policy_0776

# Auto-generated policy 776 (Rego v1 syntax)
# Package: security.authentication.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0776",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0776_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0776_allowed if {
    input.user.role == "admin"
}
policy_0776_allowed if {
    data.policies.security.enabled
}
default policy_0776_allowed = false
