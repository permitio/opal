package security.authorization.action.check.policy_0346

# Auto-generated policy 346
# Package: security.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0346",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0346_allowed if {
    data.policies.security.enabled
}
policy_0346_denied if {
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
