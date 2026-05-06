package access.authorization.action.validate.policy_0551

# Auto-generated policy 551
# Package: access.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0551",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0551_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0551_allowed if {
    data.policies.access.enabled
}
policy_0551_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
