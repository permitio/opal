package access.authentication.policy.deny.helpers.policy_0650

# Auto-generated policy 650
# Package: access.authentication.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0650",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0650_allowed if {
    input.user.active
    input.resource.public
}
policy_0650_allowed if {
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
