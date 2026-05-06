package security.monitoring.resource.validate.policy_0661

# Auto-generated policy 661
# Package: security.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0661",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0661_allowed if {
    input.user.active
    input.resource.public
}
policy_0661_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0661_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
