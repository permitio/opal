package governance.authorization.resource.validate.policy_0711

# Auto-generated policy 711 (Rego v1 syntax)
# Package: governance.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0711",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0711_allowed if {
    data.policies.governance.enabled
}
default policy_0711_allowed = false
policy_0711_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0711_allowed if {
    input.user.active
    input.resource.public
}
