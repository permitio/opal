package access.authorization.context.deny.policy_0269

# Auto-generated policy 269
# Package: access.authorization.context.deny

# Metadata
metadata := {
    "policy_id": "0269",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0269_allowed if {
    input.user.active
    input.resource.public
}
policy_0269_allowed if {
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
