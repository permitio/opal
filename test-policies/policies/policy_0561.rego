package access.monitoring.policy.allow.data.policy_0561

# Auto-generated policy 561 (Rego v1 syntax)
# Package: access.monitoring.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0561",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0561_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0561_allowed if {
    input.user.active
    input.resource.public
}
