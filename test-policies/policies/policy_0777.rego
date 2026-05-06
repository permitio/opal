package security.monitoring.context.validate.policy_0777

# Auto-generated policy 777
# Package: security.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0777",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0777_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0777_allowed if {
    input.user.role == "admin"
}
default policy_0777_allowed = false
policy_0777_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
