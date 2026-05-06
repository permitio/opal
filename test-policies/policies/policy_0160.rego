package risk.monitoring.policy.deny.policy_0160

# Auto-generated policy 160
# Package: risk.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0160",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0160_allowed if {
    data.policies.risk.enabled
}
policy_0160_allowed if {
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
