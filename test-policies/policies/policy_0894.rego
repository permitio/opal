package risk.validation.policy.check.policy_0894

# Auto-generated policy 894
# Package: risk.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0894",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0894_allowed if {
    data.policies.risk.enabled
}
policy_0894_approved if {
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
