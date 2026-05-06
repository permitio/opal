package access.authentication.action.validate.policy_0688

# Auto-generated policy 688
# Package: access.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0688",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0688_allowed if {
    data.policies.access.enabled
}
default policy_0688_allowed = false
policy_0688_allowed if {
    input.user.role == "admin"
}
policy_0688_allowed if {
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
