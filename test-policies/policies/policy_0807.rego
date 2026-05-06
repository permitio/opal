package security.enforcement.action.verify.data.policy_0807

# Auto-generated policy 807
# Package: security.enforcement.action.verify.data

# Metadata
metadata := {
    "policy_id": "0807",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0807_allowed if {
    input.user.active
    input.resource.public
}
policy_0807_allowed if {
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
