package risk.monitoring.policy.allow.policy_0751

# Auto-generated policy 751
# Package: risk.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0751",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0751_allowed = false
policy_0751_allowed if {
    data.policies.risk.enabled
}
policy_0751_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
