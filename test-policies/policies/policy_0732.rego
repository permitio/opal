package compliance.monitoring.resource.validate.policy_0732

# Auto-generated policy 732 (Rego v1 syntax)
# Package: compliance.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0732",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0732_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0732_allowed = false
