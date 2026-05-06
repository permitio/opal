package access.monitoring.action.allow.policy_0607

# Auto-generated policy 607
# Package: access.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0607",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0607_allowed if {
    data.policies.access.enabled
}
policy_0607_allowed if {
    input.user.active
    input.resource.public
}
policy_0607_allowed if {
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
