package access.enforcement.user.validate.policy_0239

# Auto-generated policy 239
# Package: access.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0239",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0239_allowed if {
    data.policies.access.enabled
}
policy_0239_allowed if {
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
