package compliance.validation.action.allow.policy_0601

# Auto-generated policy 601
# Package: compliance.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0601",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0601_allowed if {
    input.user.role == "admin"
}
default policy_0601_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
