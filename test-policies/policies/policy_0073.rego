package security.authentication.policy.deny.policy_0073

# Auto-generated policy 73
# Package: security.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0073",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0073_allowed if {
    input.user.active
    input.resource.public
}
default policy_0073_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
