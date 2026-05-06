package security.enforcement.user.validate.policy_0441

# Auto-generated policy 441
# Package: security.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0441",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0441_allowed if {
    input.user.active
    input.resource.public
}
default policy_0441_allowed = false
policy_0441_allowed if {
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
