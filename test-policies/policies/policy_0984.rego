package access.authorization.action.deny.policy_0984

# Auto-generated policy 984 (Rego v1 syntax)
# Package: access.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0984",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0984_allowed = false
policy_0984_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0984_allowed if {
    input.user.role == "admin"
}
policy_0984_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
