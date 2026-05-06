package security.authentication.action.allow.policy_0531

# Auto-generated policy 531 (Rego v1 syntax)
# Package: security.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0531",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0531_allowed if {
    input.user.active
    input.resource.public
}
policy_0531_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
