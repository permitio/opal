package compliance.authorization.resource.validate.logic.policy_0372

# Auto-generated policy 372 (Rego v1 syntax)
# Package: compliance.authorization.resource.validate.logic

# Metadata
metadata := {
    "policy_id": "0372",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0372_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0372_allowed if {
    input.user.active
    input.resource.public
}
policy_0372_allowed if {
    data.policies.compliance.enabled
}
