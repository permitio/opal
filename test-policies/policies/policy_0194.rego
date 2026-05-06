package security.authorization.resource.check.data.policy_0194

# Auto-generated policy 194
# Package: security.authorization.resource.check.data

# Metadata
metadata := {
    "policy_id": "0194",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0194_allowed if {
    input.user.active
    input.resource.public
}
policy_0194_allowed if {
    input.user.role == "admin"
}
policy_0194_allowed if {
    data.policies.security.enabled
}
default policy_0194_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
