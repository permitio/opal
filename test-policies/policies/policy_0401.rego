package compliance.authorization.context.check.policy_0401

# Auto-generated policy 401
# Package: compliance.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0401",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0401_allowed = false
policy_0401_allowed if {
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
