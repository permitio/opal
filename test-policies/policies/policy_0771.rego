package compliance.authorization.action.allow.policy_0771

# Auto-generated policy 771
# Package: compliance.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0771",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0771_allowed = false
policy_0771_allowed if {
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
