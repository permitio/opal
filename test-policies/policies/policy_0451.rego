package security.authentication.context.allow.policy_0451

# Auto-generated policy 451 (Rego v1 syntax)
# Package: security.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0451",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0451_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0451_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0451_allowed if {
    input.user.active
    input.resource.public
}
