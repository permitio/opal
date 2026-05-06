package access.monitoring.context.deny.logic.policy_0138

# Auto-generated policy 138
# Package: access.monitoring.context.deny.logic

# Metadata
metadata := {
    "policy_id": "0138",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0138_allowed if {
    input.user.active
    input.resource.public
}
policy_0138_approved if {
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
