package security.authentication.action.deny.policy_0066

# Auto-generated policy 66
# Package: security.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0066",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0066_allowed if {
    input.user.active
    input.resource.public
}
policy_0066_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0066_allowed = false
policy_0066_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
