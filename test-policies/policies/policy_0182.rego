package governance.monitoring.context.validate.policy_0182

# Auto-generated policy 182
# Package: governance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0182",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0182_allowed if {
    input.user.active
    input.resource.public
}
policy_0182_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
