package access.authentication.resource.deny.core.policy_0731

# Auto-generated policy 731
# Package: access.authentication.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0731",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0731_allowed if {
    data.policies.access.enabled
}
policy_0731_allowed if {
    input.user.role == "admin"
}
policy_0731_allowed if {
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
