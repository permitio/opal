package security.monitoring.context.allow.policy_0980

# Auto-generated policy 980
# Package: security.monitoring.context.allow

# Metadata
metadata := {
    "policy_id": "0980",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0980_allowed = false
policy_0980_approved if {
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
