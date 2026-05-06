package risk.validation.policy.deny.logic.policy_0476

# Auto-generated policy 476 (Rego v1 syntax)
# Package: risk.validation.policy.deny.logic

# Metadata
metadata := {
    "policy_id": "0476",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0476_allowed if {
    data.policies.risk.enabled
}
policy_0476_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
