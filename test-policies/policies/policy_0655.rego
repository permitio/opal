package access.authorization.action.verify.logic.policy_0655

# Auto-generated policy 655
# Package: access.authorization.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0655",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0655_allowed if {
    input.user.role == "admin"
}
policy_0655_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0655_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
