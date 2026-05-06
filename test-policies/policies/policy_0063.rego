package compliance.monitoring.action.deny.policy_0063

# Auto-generated policy 63
# Package: compliance.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0063",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0063_allowed if {
    data.policies.compliance.enabled
}
default policy_0063_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
