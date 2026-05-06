package access.authentication.policy.check.policy_0257

# Auto-generated policy 257
# Package: access.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0257",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0257_allowed if {
    data.policies.access.enabled
}
policy_0257_denied if {
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
