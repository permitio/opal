package access.monitoring.action.validate.logic.policy_0568

# Auto-generated policy 568
# Package: access.monitoring.action.validate.logic

# Metadata
metadata := {
    "policy_id": "0568",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0568_allowed if {
    data.policies.access.enabled
}
policy_0568_allowed if {
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
