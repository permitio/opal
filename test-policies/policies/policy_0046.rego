package governance.monitoring.user.allow.utils.policy_0046

# Auto-generated policy 46
# Package: governance.monitoring.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0046",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0046_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0046_allowed if {
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
