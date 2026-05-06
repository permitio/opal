package audit.validation.context.allow.data.policy_0657

# Auto-generated policy 657
# Package: audit.validation.context.allow.data

# Metadata
metadata := {
    "policy_id": "0657",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0657_allowed = false
policy_0657_denied if {
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
