package governance.validation.policy.deny.policy_0520

# Auto-generated policy 520 (Rego v1 syntax)
# Package: governance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0520",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0520_allowed if {
    data.policies.governance.enabled
}
policy_0520_allowed if {
    input.user.role == "admin"
}
