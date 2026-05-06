package governance.monitoring.action.check.policy_0816

# Auto-generated policy 816 (Rego v1 syntax)
# Package: governance.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0816",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0816_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0816_allowed = false
policy_0816_allowed if {
    data.policies.governance.enabled
}
