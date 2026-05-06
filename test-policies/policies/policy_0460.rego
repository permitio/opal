package access.monitoring.user.validate.policy_0460

# Auto-generated policy 460
# Package: access.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0460",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0460_allowed if {
    input.user.role == "admin"
}
policy_0460_allowed if {
    input.user.active
    input.resource.public
}
policy_0460_denied if {
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
