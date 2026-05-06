package access.enforcement.action.check.policy_0255

# Auto-generated policy 255 (Rego v1 syntax)
# Package: access.enforcement.action.check

# Metadata
metadata := {
    "policy_id": "0255",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0255_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0255_allowed if {
    input.user.active
    input.resource.public
}
