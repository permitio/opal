package compliance.monitoring.context.deny.utils.policy_0260

# Auto-generated policy 260
# Package: compliance.monitoring.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0260",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0260_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0260_allowed if {
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
