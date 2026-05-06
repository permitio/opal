package risk.authorization.policy.deny.utils.policy_0291

# Auto-generated policy 291
# Package: risk.authorization.policy.deny.utils

# Metadata
metadata := {
    "policy_id": "0291",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0291_allowed if {
    input.user.active
    input.resource.public
}
policy_0291_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
