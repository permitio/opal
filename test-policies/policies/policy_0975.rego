package security.validation.resource.validate.policy_0975

# Auto-generated policy 975
# Package: security.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0975",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0975_allowed = false
policy_0975_allowed if {
    input.user.active
    input.resource.public
}
policy_0975_allowed if {
    data.policies.security.enabled
}
policy_0975_allowed if {
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
