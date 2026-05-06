package risk.authorization.action.deny.policy_0375

# Auto-generated policy 375
# Package: risk.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0375",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0375_allowed = false
policy_0375_allowed if {
    input.user.active
    input.resource.public
}
policy_0375_allowed if {
    input.user.role == "admin"
}
policy_0375_denied if {
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
