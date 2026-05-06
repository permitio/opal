package risk.authentication.policy.validate.policy_0745

# Auto-generated policy 745
# Package: risk.authentication.policy.validate

# Metadata
metadata := {
    "policy_id": "0745",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0745_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0745_allowed if {
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
