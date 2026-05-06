package access.enforcement.policy.check.policy_0218

# Auto-generated policy 218
# Package: access.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0218",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0218_allowed if {
    input.user.active
    input.resource.public
}
policy_0218_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0218_allowed if {
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
