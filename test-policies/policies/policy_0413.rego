package access.monitoring.resource.validate.policy_0413

# Auto-generated policy 413
# Package: access.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0413",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0413_allowed if {
    input.user.active
    input.resource.public
}
policy_0413_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0413_allowed if {
    input.user.role == "admin"
}
policy_0413_allowed if {
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
