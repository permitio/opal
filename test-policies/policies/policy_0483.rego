package access.validation.user.validate.policy_0483

# Auto-generated policy 483
# Package: access.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0483",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0483_allowed = false
policy_0483_allowed if {
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
