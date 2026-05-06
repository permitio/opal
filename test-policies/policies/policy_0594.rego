package security.validation.user.allow.helpers.policy_0594

# Auto-generated policy 594
# Package: security.validation.user.allow.helpers

# Metadata
metadata := {
    "policy_id": "0594",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0594_allowed if {
    input.user.role == "admin"
}
default policy_0594_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
