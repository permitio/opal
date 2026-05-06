package risk.validation.policy.validate.policy_0384

# Auto-generated policy 384
# Package: risk.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0384",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0384_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0384_allowed if {
    input.user.role == "admin"
}
default policy_0384_allowed = false
policy_0384_allowed if {
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
