package governance.validation.action.allow.policy_0296

# Auto-generated policy 296
# Package: governance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0296",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0296_allowed if {
    input.user.role == "admin"
}
policy_0296_allowed if {
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
