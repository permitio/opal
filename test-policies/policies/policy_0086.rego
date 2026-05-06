package access.enforcement.resource.verify.policy_0086

# Auto-generated policy 86
# Package: access.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0086",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0086_allowed if {
    data.policies.access.enabled
}
policy_0086_allowed if {
    input.user.role == "admin"
}
policy_0086_allowed if {
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
