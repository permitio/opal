package access.authorization.resource.validate.policy_0691

# Auto-generated policy 691 (Rego v1 syntax)
# Package: access.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0691",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0691_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0691_allowed if {
    input.user.active
    input.resource.public
}
default policy_0691_allowed = false
