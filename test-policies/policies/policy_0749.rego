package access.monitoring.action.deny.policy_0749

# Auto-generated policy 749
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0749",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0749_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0749_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
