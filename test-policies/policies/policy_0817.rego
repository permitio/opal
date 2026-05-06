package security.authorization.user.verify.policy_0817

# Auto-generated policy 817
# Package: security.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0817",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0817_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0817_allowed if {
    input.user.role == "admin"
}
policy_0817_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
