package access.authorization.action.allow.policy_0686

# Auto-generated policy 686 (Rego v1 syntax)
# Package: access.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0686",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0686_allowed if {
    input.user.active
    input.resource.public
}
policy_0686_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
