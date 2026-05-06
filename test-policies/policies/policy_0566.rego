package compliance.authentication.user.allow.policy_0566

# Auto-generated policy 566
# Package: compliance.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0566",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0566_allowed if {
    input.user.active
    input.resource.public
}
default policy_0566_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
