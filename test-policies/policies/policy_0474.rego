package audit.monitoring.user.allow.policy_0474

# Auto-generated policy 474
# Package: audit.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0474",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0474_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0474_allowed if {
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
