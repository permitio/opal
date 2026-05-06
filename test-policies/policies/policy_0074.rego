package access.authorization.user.validate.policy_0074

# Auto-generated policy 74
# Package: access.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0074",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0074_allowed if {
    data.policies.access.enabled
}
default policy_0074_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
