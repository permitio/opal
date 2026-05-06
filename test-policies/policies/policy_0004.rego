package security.authentication.context.deny.logic.policy_0004

# Auto-generated policy 4 (Rego v1 syntax)
# Package: security.authentication.context.deny.logic

# Metadata
metadata := {
    "policy_id": "0004",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0004_allowed = false
policy_0004_allowed if {
    input.user.active
    input.resource.public
}
policy_0004_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0004_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
