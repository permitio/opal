package access.authorization.user.validate.policy_0433

# Auto-generated policy 433
# Package: access.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0433",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0433_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0433_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
