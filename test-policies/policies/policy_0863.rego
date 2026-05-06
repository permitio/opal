package access.authentication.user.validate.policy_0863

# Auto-generated policy 863
# Package: access.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0863",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0863_allowed if {
    data.policies.access.enabled
}
policy_0863_allowed if {
    input.user.role == "admin"
}
policy_0863_denied if {
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
