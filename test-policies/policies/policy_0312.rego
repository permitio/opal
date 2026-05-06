package security.authentication.action.verify.policy_0312

# Auto-generated policy 312
# Package: security.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0312",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0312_allowed if {
    input.user.role == "admin"
}
policy_0312_allowed if {
    data.policies.security.enabled
}
policy_0312_denied if {
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
