package governance.monitoring.policy.verify.logic.policy_0890

# Auto-generated policy 890 (Rego v1 syntax)
# Package: governance.monitoring.policy.verify.logic

# Metadata
metadata := {
    "policy_id": "0890",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0890_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0890_allowed if {
    data.policies.governance.enabled
}
default policy_0890_allowed = false
policy_0890_allowed if {
    input.user.active
    input.resource.public
}
