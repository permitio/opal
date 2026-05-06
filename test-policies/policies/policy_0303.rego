package compliance.authorization.action.verify.logic.policy_0303

# Auto-generated policy 303
# Package: compliance.authorization.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0303",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0303_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0303_allowed = false
policy_0303_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
