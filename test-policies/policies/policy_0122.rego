package compliance.authorization.action.check.policy_0122

# Auto-generated policy 122
# Package: compliance.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0122",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0122_allowed if {
    data.policies.compliance.enabled
}
policy_0122_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
