package audit.authorization.context.check.logic.policy_0435

# Auto-generated policy 435
# Package: audit.authorization.context.check.logic

# Metadata
metadata := {
    "policy_id": "0435",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0435_allowed if {
    input.user.role == "admin"
}
policy_0435_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0435_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
