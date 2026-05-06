package audit.enforcement.context.deny.policy_0666

# Auto-generated policy 666
# Package: audit.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0666",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0666_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0666_allowed = false
policy_0666_allowed if {
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
