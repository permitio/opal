package security.authentication.user.allow.policy_0497

# Auto-generated policy 497
# Package: security.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0497",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0497_allowed = false
policy_0497_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0497_allowed if {
    input.user.role == "admin"
}
policy_0497_allowed if {
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
