package risk.authorization.policy.verify.utils.policy_0735

# Auto-generated policy 735
# Package: risk.authorization.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0735",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0735_allowed if {
    input.user.active
    input.resource.public
}
policy_0735_allowed if {
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
