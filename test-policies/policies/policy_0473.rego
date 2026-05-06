package access.validation.action.verify.core.policy_0473

# Auto-generated policy 473
# Package: access.validation.action.verify.core

# Metadata
metadata := {
    "policy_id": "0473",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0473_allowed if {
    data.policies.access.enabled
}
default policy_0473_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
