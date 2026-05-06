package risk.authorization.resource.check.helpers.policy_0433

# Auto-generated policy 433 (Rego v1 syntax)
# Package: risk.authorization.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0433",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0433_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0433_allowed if {
    data.policies.risk.enabled
}
