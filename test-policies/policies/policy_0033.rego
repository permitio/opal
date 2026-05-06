package security.authorization.policy.allow.logic.policy_0033

# Auto-generated policy 33
# Package: security.authorization.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0033",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0033_allowed if {
    data.policies.security.enabled
}
policy_0033_allowed if {
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
