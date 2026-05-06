package access.monitoring.user.validate.policy_0945

# Auto-generated policy 945
# Package: access.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0945",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0945_allowed = false
policy_0945_allowed if {
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
