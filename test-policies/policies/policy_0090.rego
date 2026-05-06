package risk.monitoring.policy.deny.utils.policy_0090

# Auto-generated policy 90
# Package: risk.monitoring.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0090",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0090_allowed if {
    input.user.role == "admin"
}
policy_0090_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0090_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
