package compliance.monitoring.action.allow.policy_0464

# Auto-generated policy 464
# Package: compliance.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0464",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0464_allowed if {
    input.user.active
    input.resource.public
}
default policy_0464_allowed = false
policy_0464_approved if {
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
