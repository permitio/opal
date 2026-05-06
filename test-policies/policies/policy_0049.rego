package security.validation.resource.validate.helpers.policy_0049

# Auto-generated policy 49
# Package: security.validation.resource.validate.helpers

# Metadata
metadata := {
    "policy_id": "0049",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0049_allowed = false
policy_0049_allowed if {
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
