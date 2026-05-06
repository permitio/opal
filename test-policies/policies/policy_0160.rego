package risk.authorization.policy.deny.logic.policy_0160

# Auto-generated policy 160 (Rego v1 syntax)
# Package: risk.authorization.policy.deny.logic

# Metadata
metadata := {
    "policy_id": "0160",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0160_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0160_allowed if {
    data.policies.risk.enabled
}
policy_0160_allowed if {
    input.user.active
    input.resource.public
}
