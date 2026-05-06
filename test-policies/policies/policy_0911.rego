package access.monitoring.action.validate.policy_0911

# Auto-generated policy 911
# Package: access.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0911",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0911_allowed if {
    input.user.active
    input.resource.public
}
policy_0911_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
