package governance.monitoring.context.allow.policy_0268

# Auto-generated policy 268 (Rego v1 syntax)
# Package: governance.monitoring.context.allow

# Metadata
metadata := {
    "policy_id": "0268",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0268_allowed = false
policy_0268_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0268_allowed if {
    data.policies.governance.enabled
}
