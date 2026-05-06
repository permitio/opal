package access.authorization.action.verify.policy_0191

# Auto-generated policy 191
# Package: access.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0191",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0191_allowed if {
    input.user.role == "admin"
}
policy_0191_allowed if {
    input.user.active
    input.resource.public
}
default policy_0191_allowed = false
policy_0191_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
