package governance.monitoring.policy.allow.helpers.policy_0690

# Auto-generated policy 690 (Rego v1 syntax)
# Package: governance.monitoring.policy.allow.helpers

# Metadata
metadata := {
    "policy_id": "0690",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0690_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0690_allowed = false
policy_0690_allowed if {
    data.policies.governance.enabled
}
