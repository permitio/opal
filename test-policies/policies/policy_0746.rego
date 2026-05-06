package access.authorization.context.validate.policy_0746

# Auto-generated policy 746 (Rego v1 syntax)
# Package: access.authorization.context.validate

# Metadata
metadata := {
    "policy_id": "0746",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0746_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0746_allowed if {
    input.user.role == "admin"
}
default policy_0746_allowed = false
