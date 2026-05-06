package access.authorization.user.validate.core.policy_0414

# Auto-generated policy 414
# Package: access.authorization.user.validate.core

# Metadata
metadata := {
    "policy_id": "0414",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0414_allowed if {
    input.user.active
    input.resource.public
}
default policy_0414_allowed = false
policy_0414_denied if {
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
