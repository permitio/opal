package audit.validation.user.allow.policy_0038

# Auto-generated policy 38
# Package: audit.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0038",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0038_allowed = false
policy_0038_allowed if {
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
