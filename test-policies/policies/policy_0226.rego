package security.validation.policy.check.helpers.policy_0226

# Auto-generated policy 226
# Package: security.validation.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0226",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0226_allowed = false
policy_0226_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
