package risk.monitoring.action.deny.core.policy_0276

# Auto-generated policy 276
# Package: risk.monitoring.action.deny.core

# Metadata
metadata := {
    "policy_id": "0276",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0276_allowed if {
    input.user.role == "admin"
}
default policy_0276_allowed = false
policy_0276_allowed if {
    data.policies.risk.enabled
}
policy_0276_approved if {
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
