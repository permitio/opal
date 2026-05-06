package governance.monitoring.user.validate.logic.policy_0094

# Auto-generated policy 94
# Package: governance.monitoring.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0094",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0094_allowed if {
    input.user.active
    input.resource.public
}
policy_0094_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0094_allowed if {
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
