package governance.authorization.policy.validate.policy_0738

# Auto-generated policy 738
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0738",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0738_allowed if {
    data.policies.governance.enabled
}
policy_0738_allowed if {
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
