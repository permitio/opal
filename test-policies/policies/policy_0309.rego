package access.enforcement.context.validate.policy_0309

# Auto-generated policy 309
# Package: access.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0309",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0309_allowed if {
    input.user.role == "admin"
}
policy_0309_allowed if {
    data.policies.access.enabled
}
policy_0309_allowed if {
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
