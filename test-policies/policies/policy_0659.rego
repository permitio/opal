package security.authorization.resource.allow.helpers.policy_0659

# Auto-generated policy 659
# Package: security.authorization.resource.allow.helpers

# Metadata
metadata := {
    "policy_id": "0659",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0659_allowed if {
    input.user.role == "admin"
}
policy_0659_allowed if {
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
