package audit.enforcement.context.deny.policy_0104

# Auto-generated policy 104
# Package: audit.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0104",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0104_allowed = false
policy_0104_denied if {
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
