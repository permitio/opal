package governance.monitoring.action.allow.core.policy_0658

# Auto-generated policy 658 (Rego v1 syntax)
# Package: governance.monitoring.action.allow.core

# Metadata
metadata := {
    "policy_id": "0658",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0658_allowed = false
policy_0658_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0658_allowed if {
    data.policies.governance.enabled
}
policy_0658_allowed if {
    input.user.active
    input.resource.public
}
