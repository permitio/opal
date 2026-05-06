package compliance.monitoring.policy.deny.helpers.policy_0153

# Auto-generated policy 153 (Rego v1 syntax)
# Package: compliance.monitoring.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0153",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0153_allowed if {
    input.user.role == "admin"
}
policy_0153_allowed if {
    data.policies.compliance.enabled
}
default policy_0153_allowed = false
