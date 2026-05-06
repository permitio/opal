package audit.enforcement.action.validate.policy_0763

# Auto-generated policy 763 (Rego v1 syntax)
# Package: audit.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0763",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0763_allowed = false
policy_0763_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
