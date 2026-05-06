package risk.authorization.policy.deny.policy_0332

# Auto-generated policy 332 (Rego v1 syntax)
# Package: risk.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0332",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0332_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0332_allowed if {
    input.user.active
    input.resource.public
}
