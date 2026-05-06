package access.monitoring.action.allow.data.policy_0569

# Auto-generated policy 569
# Package: access.monitoring.action.allow.data

# Metadata
metadata := {
    "policy_id": "0569",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0569_allowed if {
    data.policies.access.enabled
}
policy_0569_approved if {
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
