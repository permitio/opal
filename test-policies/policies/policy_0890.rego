package access.monitoring.policy.deny.helpers.policy_0890

# Auto-generated policy 890
# Package: access.monitoring.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0890",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0890_allowed if {
    input.user.role == "admin"
}
default policy_0890_allowed = false
policy_0890_allowed if {
    data.policies.access.enabled
}
policy_0890_approved if {
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
