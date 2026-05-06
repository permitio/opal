package access.validation.resource.verify.policy_0429

# Auto-generated policy 429
# Package: access.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0429",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0429_allowed if {
    input.user.role == "admin"
}
default policy_0429_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
