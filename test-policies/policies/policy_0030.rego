package access.monitoring.user.validate.logic.policy_0030

# Auto-generated policy 30
# Package: access.monitoring.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0030",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0030_allowed if {
    input.user.role == "admin"
}
default policy_0030_allowed = false
policy_0030_approved if {
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
