package access.monitoring.action.check.policy_0298

# Auto-generated policy 298
# Package: access.monitoring.action.check

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
policy_0298_allowed if {
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
