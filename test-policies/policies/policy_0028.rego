package security.monitoring.policy.validate.utils.policy_0028

# Auto-generated policy 28 (Rego v1 syntax)
# Package: security.monitoring.policy.validate.utils

# Metadata
metadata := {
    "policy_id": "0028",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0028_allowed = false
policy_0028_allowed if {
    data.policies.security.enabled
}
policy_0028_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
