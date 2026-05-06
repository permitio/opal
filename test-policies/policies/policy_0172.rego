package compliance.authorization.action.validate.policy_0172

# Auto-generated policy 172 (Rego v1 syntax)
# Package: compliance.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0172",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0172_allowed if {
    input.user.active
    input.resource.public
}
policy_0172_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0172_allowed = false
policy_0172_allowed if {
    data.policies.compliance.enabled
}
