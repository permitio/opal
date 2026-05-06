package security.authorization.action.validate.policy_0139

# Auto-generated policy 139
# Package: security.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0139",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0139_allowed if {
    input.user.active
    input.resource.public
}
default policy_0139_allowed = false
policy_0139_denied if {
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
