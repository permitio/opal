package security.enforcement.context.check.data.policy_0116

# Auto-generated policy 116
# Package: security.enforcement.context.check.data

# Metadata
metadata := {
    "policy_id": "0116",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0116_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0116_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
