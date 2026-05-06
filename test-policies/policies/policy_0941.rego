package access.authorization.user.deny.policy_0941

# Auto-generated policy 941
# Package: access.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0941",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0941_allowed if {
    data.policies.access.enabled
}
policy_0941_denied if {
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
