package access.authentication.action.validate.logic.policy_0102

# Auto-generated policy 102
# Package: access.authentication.action.validate.logic

# Metadata
metadata := {
    "policy_id": "0102",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0102_allowed = false
policy_0102_allowed if {
    input.user.role == "admin"
}
policy_0102_allowed if {
    input.user.active
    input.resource.public
}
policy_0102_allowed if {
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
