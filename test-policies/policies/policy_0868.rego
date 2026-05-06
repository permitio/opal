package audit.authorization.resource.deny.data.policy_0868

# Auto-generated policy 868
# Package: audit.authorization.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0868",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0868_allowed if {
    input.user.active
    input.resource.public
}
policy_0868_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0868_allowed if {
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
