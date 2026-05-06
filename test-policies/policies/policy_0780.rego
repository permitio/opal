package access.monitoring.action.deny.utils.policy_0780

# Auto-generated policy 780
# Package: access.monitoring.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0780",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0780_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0780_allowed = false
policy_0780_allowed if {
    data.policies.access.enabled
}
policy_0780_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
