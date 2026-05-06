package audit.monitoring.context.deny.policy_0795

# Auto-generated policy 795
# Package: audit.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0795",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0795_allowed if {
    input.user.role == "admin"
}
default policy_0795_allowed = false
policy_0795_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0795_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
