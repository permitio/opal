package audit.authentication.context.allow.policy_0334

# Auto-generated policy 334
# Package: audit.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0334",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0334_allowed = false
policy_0334_denied if {
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
