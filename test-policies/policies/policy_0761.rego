package access.enforcement.user.validate.policy_0761

# Auto-generated policy 761
# Package: access.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0761",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0761_allowed if {
    data.policies.access.enabled
}
default policy_0761_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
