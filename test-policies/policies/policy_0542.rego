package access.validation.action.check.policy_0542

# Auto-generated policy 542
# Package: access.validation.action.check

# Metadata
metadata := {
    "policy_id": "0542",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0542_allowed if {
    input.user.role == "admin"
}
policy_0542_allowed if {
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
