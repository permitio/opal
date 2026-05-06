package risk.monitoring.policy.check.policy_0423

# Auto-generated policy 423 (Rego v1 syntax)
# Package: risk.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0423",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0423_allowed if {
    input.user.active
    input.resource.public
}
policy_0423_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
