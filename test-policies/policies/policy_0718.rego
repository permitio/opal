package compliance.authentication.action.validate.policy_0718

# Auto-generated policy 718 (Rego v1 syntax)
# Package: compliance.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0718",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0718_allowed if {
    input.user.active
    input.resource.public
}
policy_0718_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0718_allowed if {
    data.policies.compliance.enabled
}
