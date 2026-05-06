package access.monitoring.action.verify.policy_0809

# Auto-generated policy 809
# Package: access.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0809",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0809_allowed if {
    input.user.role == "admin"
}
policy_0809_allowed if {
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
