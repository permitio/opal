package governance.monitoring.resource.verify.policy_0860

# Auto-generated policy 860 (Rego v1 syntax)
# Package: governance.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0860",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0860_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0860_allowed if {
    input.user.active
    input.resource.public
}
