package access.enforcement.action.deny.policy_0225

# Auto-generated policy 225
# Package: access.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0225",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0225_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0225_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
