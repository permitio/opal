package access.authentication.action.check.data.policy_0989

# Auto-generated policy 989
# Package: access.authentication.action.check.data

# Metadata
metadata := {
    "policy_id": "0989",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0989_allowed = false
policy_0989_allowed if {
    data.policies.access.enabled
}
policy_0989_allowed if {
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
