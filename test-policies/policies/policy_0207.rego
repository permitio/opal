package security.monitoring.action.validate.utils.policy_0207

# Auto-generated policy 207
# Package: security.monitoring.action.validate.utils

# Metadata
metadata := {
    "policy_id": "0207",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0207_allowed = false
policy_0207_allowed if {
    input.user.role == "admin"
}
policy_0207_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
