package access.authorization.context.verify.data.policy_0042

# Auto-generated policy 42
# Package: access.authorization.context.verify.data

# Metadata
metadata := {
    "policy_id": "0042",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0042_allowed if {
    input.user.active
    input.resource.public
}
policy_0042_allowed if {
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
