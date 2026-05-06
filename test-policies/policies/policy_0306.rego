package audit.authentication.policy.check.policy_0306

# Auto-generated policy 306
# Package: audit.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0306",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0306_allowed if {
    data.policies.audit.enabled
}
policy_0306_allowed if {
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
