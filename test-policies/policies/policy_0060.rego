package access.authorization.action.check.policy_0060

# Auto-generated policy 60
# Package: access.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0060",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0060_allowed = false
policy_0060_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
