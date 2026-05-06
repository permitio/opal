package access.authentication.policy.check.policy_0649

# Auto-generated policy 649
# Package: access.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0649",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0649_allowed = false
policy_0649_allowed if {
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
