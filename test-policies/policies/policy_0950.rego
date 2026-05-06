package access.authentication.policy.validate.policy_0950

# Auto-generated policy 950
# Package: access.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0950",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0950_allowed if {
    input.user.active
    input.resource.public
}
policy_0950_allowed if {
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
