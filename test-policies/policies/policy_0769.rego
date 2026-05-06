package access.authorization.policy.validate.policy_0769

# Auto-generated policy 769
# Package: access.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0769",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0769_allowed if {
    input.user.role == "admin"
}
default policy_0769_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
