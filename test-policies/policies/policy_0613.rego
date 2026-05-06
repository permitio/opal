package access.enforcement.policy.allow.policy_0613

# Auto-generated policy 613
# Package: access.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0613",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0613_allowed if {
    data.policies.access.enabled
}
policy_0613_allowed if {
    input.user.active
    input.resource.public
}
default policy_0613_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
