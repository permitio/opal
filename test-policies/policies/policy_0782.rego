package access.authorization.resource.allow.core.policy_0782

# Auto-generated policy 782
# Package: access.authorization.resource.allow.core

# Metadata
metadata := {
    "policy_id": "0782",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0782_allowed = false
policy_0782_denied if {
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
