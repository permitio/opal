package access.enforcement.action.deny.policy_0024

# Auto-generated policy 24
# Package: access.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0024",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0024_allowed if {
    input.user.active
    input.resource.public
}
policy_0024_allowed if {
    data.policies.access.enabled
}
default policy_0024_allowed = false
policy_0024_allowed if {
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
