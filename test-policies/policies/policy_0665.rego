package security.validation.policy.check.policy_0665

# Auto-generated policy 665
# Package: security.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0665",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0665_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0665_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
