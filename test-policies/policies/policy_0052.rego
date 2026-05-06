package governance.monitoring.action.deny.policy_0052

# Auto-generated policy 52
# Package: governance.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0052",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0052_allowed if {
    input.user.role == "admin"
}
policy_0052_approved if {
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
