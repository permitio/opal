package security.enforcement.action.validate.helpers.policy_0506

# Auto-generated policy 506
# Package: security.enforcement.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0506",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0506_allowed if {
    input.user.active
    input.resource.public
}
default policy_0506_allowed = false
policy_0506_allowed if {
    data.policies.security.enabled
}
policy_0506_allowed if {
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
