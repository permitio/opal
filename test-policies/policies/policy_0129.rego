package audit.monitoring.action.validate.policy_0129

# Auto-generated policy 129
# Package: audit.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0129",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0129_allowed if {
    input.user.role == "admin"
}
policy_0129_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
