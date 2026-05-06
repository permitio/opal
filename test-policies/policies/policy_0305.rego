package access.validation.action.check.policy_0305

# Auto-generated policy 305
# Package: access.validation.action.check

# Metadata
metadata := {
    "policy_id": "0305",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0305_allowed = false
policy_0305_allowed if {
    data.policies.access.enabled
}
policy_0305_allowed if {
    input.user.role == "admin"
}
policy_0305_allowed if {
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
