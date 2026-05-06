package access.monitoring.action.deny.policy_0457

# Auto-generated policy 457
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0457",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0457_allowed if {
    input.user.role == "admin"
}
policy_0457_allowed if {
    input.user.active
    input.resource.public
}
policy_0457_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0457_allowed if {
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
