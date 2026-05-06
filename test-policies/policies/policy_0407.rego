package risk.monitoring.action.allow.policy_0407

# Auto-generated policy 407
# Package: risk.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0407",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0407_allowed if {
    data.policies.risk.enabled
}
default policy_0407_allowed = false
policy_0407_approved if {
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
