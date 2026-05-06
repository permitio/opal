package security.monitoring.resource.allow.policy_0055

# Auto-generated policy 55
# Package: security.monitoring.resource.allow

# Metadata
metadata := {
    "policy_id": "0055",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0055_allowed if {
    input.user.active
    input.resource.public
}
policy_0055_denied if {
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
