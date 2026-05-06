package access.enforcement.action.validate.policy_0623

# Auto-generated policy 623
# Package: access.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0623",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0623_allowed if {
    input.user.role == "admin"
}
policy_0623_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0623_allowed = false
policy_0623_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
