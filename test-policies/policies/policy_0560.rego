package risk.authorization.user.validate.policy_0560

# Auto-generated policy 560
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0560",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0560_allowed if {
    data.policies.risk.enabled
}
policy_0560_allowed if {
    input.user.active
    input.resource.public
}
policy_0560_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
