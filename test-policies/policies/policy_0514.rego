package access.authentication.context.validate.policy_0514

# Auto-generated policy 514 (Rego v1 syntax)
# Package: access.authentication.context.validate

# Metadata
metadata := {
    "policy_id": "0514",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0514_allowed if {
    input.user.active
    input.resource.public
}
policy_0514_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0514_allowed = false
