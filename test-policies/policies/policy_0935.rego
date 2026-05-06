package access.validation.context.validate.policy_0935

# Auto-generated policy 935
# Package: access.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0935",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0935_allowed = false
policy_0935_allowed if {
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
