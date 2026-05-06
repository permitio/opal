package risk.monitoring.user.validate.policy_0556

# Auto-generated policy 556
# Package: risk.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0556",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0556_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0556_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
