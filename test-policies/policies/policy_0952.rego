package risk.monitoring.action.check.utils.policy_0952

# Auto-generated policy 952
# Package: risk.monitoring.action.check.utils

# Metadata
metadata := {
    "policy_id": "0952",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0952_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0952_allowed if {
    data.policies.risk.enabled
}
policy_0952_allowed if {
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
