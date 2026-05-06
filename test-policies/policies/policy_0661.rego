package governance.monitoring.user.verify.policy_0661

# Auto-generated policy 661 (Rego v1 syntax)
# Package: governance.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0661",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0661_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0661_allowed if {
    input.user.active
    input.resource.public
}
