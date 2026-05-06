package security.monitoring.policy.deny.policy_0479

# Auto-generated policy 479 (Rego v1 syntax)
# Package: security.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0479",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0479_allowed if {
    data.policies.security.enabled
}
policy_0479_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
