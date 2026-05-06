package security.validation.context.validate.policy_0813

# Auto-generated policy 813 (Rego v1 syntax)
# Package: security.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0813",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0813_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0813_allowed = false
policy_0813_allowed if {
    input.user.role == "admin"
}
policy_0813_allowed if {
    data.policies.security.enabled
}
