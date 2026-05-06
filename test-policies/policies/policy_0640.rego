package security.validation.action.verify.helpers.policy_0640

# Auto-generated policy 640
# Package: security.validation.action.verify.helpers

# Metadata
metadata := {
    "policy_id": "0640",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0640_allowed if {
    data.policies.security.enabled
}
policy_0640_denied if {
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
