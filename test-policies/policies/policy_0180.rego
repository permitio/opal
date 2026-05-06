package risk.authentication.context.deny.policy_0180

# Auto-generated policy 180 (Rego v1 syntax)
# Package: risk.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0180",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0180_allowed = false
policy_0180_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0180_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0180_allowed if {
    input.user.active
    input.resource.public
}
