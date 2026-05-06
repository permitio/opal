package security.validation.action.check.policy_0188

# Auto-generated policy 188
# Package: security.validation.action.check

# Metadata
metadata := {
    "policy_id": "0188",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0188_allowed if {
    data.policies.security.enabled
}
default policy_0188_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
