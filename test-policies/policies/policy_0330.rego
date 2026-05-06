package audit.authentication.action.validate.policy_0330

# Auto-generated policy 330
# Package: audit.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0330",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0330_allowed if {
    data.policies.audit.enabled
}
policy_0330_allowed if {
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
