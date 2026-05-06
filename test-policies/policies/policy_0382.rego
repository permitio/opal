package access.authentication.policy.validate.data.policy_0382

# Auto-generated policy 382
# Package: access.authentication.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0382",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0382_allowed if {
    data.policies.access.enabled
}
policy_0382_allowed if {
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
