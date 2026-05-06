package access.monitoring.policy.deny.policy_0500

# Auto-generated policy 500
# Package: access.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0500",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0500_allowed if {
    data.policies.access.enabled
}
policy_0500_allowed if {
    input.user.role == "admin"
}
policy_0500_allowed if {
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
