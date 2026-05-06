package risk.authorization.policy.deny.policy_0298

# Auto-generated policy 298 (Rego v1 syntax)
# Package: risk.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0298",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0298_allowed if {
    input.user.active
    input.resource.public
}
policy_0298_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0298_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0298_allowed if {
    input.user.role == "admin"
}
