package governance.authorization.context.verify.policy_0110

# Auto-generated policy 110 (Rego v1 syntax)
# Package: governance.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0110",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0110_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0110_allowed if {
    input.user.active
    input.resource.public
}
policy_0110_allowed if {
    data.policies.governance.enabled
}
