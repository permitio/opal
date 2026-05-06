package security.authorization.user.deny.policy_0096

# Auto-generated policy 96
# Package: security.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0096",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0096_allowed if {
    input.user.active
    input.resource.public
}
default policy_0096_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
