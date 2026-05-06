package governance.authentication.context.verify.logic.policy_0300

# Auto-generated policy 300
# Package: governance.authentication.context.verify.logic

# Metadata
metadata := {
    "policy_id": "0300",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0300_allowed if {
    input.user.role == "admin"
}
policy_0300_approved if {
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
