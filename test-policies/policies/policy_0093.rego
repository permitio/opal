package governance.authorization.policy.allow.policy_0093

# Auto-generated policy 93
# Package: governance.authorization.policy.allow

# Metadata
metadata := {
    "policy_id": "0093",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0093_allowed = false
policy_0093_allowed if {
    input.user.active
    input.resource.public
}
policy_0093_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
