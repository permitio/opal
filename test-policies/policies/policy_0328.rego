package access.enforcement.user.check.data.policy_0328

# Auto-generated policy 328
# Package: access.enforcement.user.check.data

# Metadata
metadata := {
    "policy_id": "0328",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0328_allowed if {
    input.user.role == "admin"
}
policy_0328_denied if {
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
