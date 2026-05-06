package compliance.validation.resource.validate.policy_0066

# Auto-generated policy 66 (Rego v1 syntax)
# Package: compliance.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0066",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0066_allowed = false
policy_0066_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
