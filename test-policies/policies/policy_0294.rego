package risk.monitoring.policy.verify.helpers.policy_0294

# Auto-generated policy 294 (Rego v1 syntax)
# Package: risk.monitoring.policy.verify.helpers

# Metadata
metadata := {
    "policy_id": "0294",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0294_allowed if {
    input.user.active
    input.resource.public
}
policy_0294_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
