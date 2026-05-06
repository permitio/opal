package access.monitoring.user.validate.policy_0820

# Auto-generated policy 820
# Package: access.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0820",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0820_allowed if {
    data.policies.access.enabled
}
policy_0820_allowed if {
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
