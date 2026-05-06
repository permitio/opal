package security.authorization.user.deny.policy_0857

# Auto-generated policy 857
# Package: security.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0857",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0857_allowed if {
    input.user.role == "admin"
}
policy_0857_denied if {
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
