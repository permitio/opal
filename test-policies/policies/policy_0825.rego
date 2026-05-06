package audit.authorization.action.deny.data.policy_0825

# Auto-generated policy 825 (Rego v1 syntax)
# Package: audit.authorization.action.deny.data

# Metadata
metadata := {
    "policy_id": "0825",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0825_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0825_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0825_allowed = false
