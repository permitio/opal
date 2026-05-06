package compliance.validation.user.allow.helpers.policy_0115

# Auto-generated policy 115 (Rego v1 syntax)
# Package: compliance.validation.user.allow.helpers

# Metadata
metadata := {
    "policy_id": "0115",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0115_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0115_allowed if {
    input.user.active
    input.resource.public
}
policy_0115_allowed if {
    data.policies.compliance.enabled
}
