package security.validation.resource.validate.policy_0978

# Auto-generated policy 978
# Package: security.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0978",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0978_allowed if {
    input.user.active
    input.resource.public
}
policy_0978_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0978_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
