package access.authentication.resource.validate.policy_0767

# Auto-generated policy 767
# Package: access.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0767",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0767_allowed = false
policy_0767_allowed if {
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
