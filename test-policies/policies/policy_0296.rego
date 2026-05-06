package compliance.authorization.user.validate.policy_0296

# Auto-generated policy 296 (Rego v1 syntax)
# Package: compliance.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0296",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0296_allowed = false
policy_0296_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0296_allowed if {
    data.policies.compliance.enabled
}
