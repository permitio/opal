package access.monitoring.user.allow.policy_0543

# Auto-generated policy 543
# Package: access.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0543",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0543_allowed = false
policy_0543_denied if {
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
