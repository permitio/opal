package security.monitoring.user.validate.logic.policy_0451

# Auto-generated policy 451
# Package: security.monitoring.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0451",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0451_allowed if {
    input.user.role == "admin"
}
policy_0451_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0451_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
