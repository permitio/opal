package access.authentication.action.allow.logic.policy_0150

# Auto-generated policy 150 (Rego v1 syntax)
# Package: access.authentication.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0150",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0150_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0150_allowed if {
    input.user.role == "admin"
}
default policy_0150_allowed = false
policy_0150_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
