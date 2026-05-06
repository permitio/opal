package governance.monitoring.policy.deny.data.policy_0306

# Auto-generated policy 306 (Rego v1 syntax)
# Package: governance.monitoring.policy.deny.data

# Metadata
metadata := {
    "policy_id": "0306",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0306_allowed = false
policy_0306_allowed if {
    data.policies.governance.enabled
}
policy_0306_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0306_allowed if {
    input.user.active
    input.resource.public
}
