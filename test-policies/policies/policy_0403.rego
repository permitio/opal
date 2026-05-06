package risk.validation.policy.deny.data.policy_0403

# Auto-generated policy 403
# Package: risk.validation.policy.deny.data

# Metadata
metadata := {
    "policy_id": "0403",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0403_allowed if {
    data.policies.risk.enabled
}
policy_0403_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0403_allowed if {
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
