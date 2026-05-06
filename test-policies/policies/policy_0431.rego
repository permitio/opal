package governance.authentication.policy.allow.utils.policy_0431

# Auto-generated policy 431
# Package: governance.authentication.policy.allow.utils

# Metadata
metadata := {
    "policy_id": "0431",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0431_allowed if {
    input.user.role == "admin"
}
default policy_0431_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
