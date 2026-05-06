package security.monitoring.action.deny.policy_0374

# Auto-generated policy 374
# Package: security.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0374",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0374_allowed if {
    input.user.active
    input.resource.public
}
policy_0374_denied if {
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
