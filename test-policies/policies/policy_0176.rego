package security.authentication.user.validate.policy_0176

# Auto-generated policy 176
# Package: security.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0176",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0176_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0176_allowed = false
policy_0176_allowed if {
    input.user.active
    input.resource.public
}
policy_0176_allowed if {
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
