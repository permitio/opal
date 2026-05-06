package access.authorization.action.allow.policy_0112

# Auto-generated policy 112
# Package: access.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0112",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0112_allowed if {
    data.policies.access.enabled
}
policy_0112_allowed if {
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
