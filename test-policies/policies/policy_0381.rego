package compliance.authorization.action.allow.utils.policy_0381

# Auto-generated policy 381
# Package: compliance.authorization.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0381",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0381_allowed if {
    input.user.role == "admin"
}
policy_0381_denied if {
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
