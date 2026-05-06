package access.validation.policy.validate.policy_0325

# Auto-generated policy 325
# Package: access.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0325",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0325_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0325_allowed if {
    input.user.role == "admin"
}
policy_0325_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
