package access.validation.policy.allow.policy_0380

# Auto-generated policy 380
# Package: access.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0380",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0380_allowed if {
    input.user.active
    input.resource.public
}
policy_0380_allowed if {
    input.user.role == "admin"
}
policy_0380_allowed if {
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
