package security.monitoring.resource.validate.policy_0295

# Auto-generated policy 295
# Package: security.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0295",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0295_allowed if {
    input.user.role == "admin"
}
policy_0295_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
