package compliance.enforcement.action.verify.policy_0587

# Auto-generated policy 587
# Package: compliance.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0587",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0587_allowed = false
policy_0587_allowed if {
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
