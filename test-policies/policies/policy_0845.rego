package access.authentication.policy.validate.policy_0845

# Auto-generated policy 845
# Package: access.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0845",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0845_allowed if {
    input.user.active
    input.resource.public
}
policy_0845_denied if {
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
