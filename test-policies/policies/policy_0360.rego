package security.validation.resource.check.policy_0360

# Auto-generated policy 360 (Rego v1 syntax)
# Package: security.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0360",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0360_allowed if {
    input.user.active
    input.resource.public
}
default policy_0360_allowed = false
policy_0360_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
