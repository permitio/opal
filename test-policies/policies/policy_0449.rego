package access.monitoring.policy.validate.data.policy_0449

# Auto-generated policy 449
# Package: access.monitoring.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0449",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0449_allowed = false
policy_0449_allowed if {
    input.user.active
    input.resource.public
}
policy_0449_allowed if {
    data.policies.access.enabled
}
policy_0449_allowed if {
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
