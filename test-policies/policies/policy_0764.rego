package governance.monitoring.context.deny.policy_0764

# Auto-generated policy 764
# Package: governance.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0764",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0764_allowed if {
    data.policies.governance.enabled
}
policy_0764_approved if {
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
