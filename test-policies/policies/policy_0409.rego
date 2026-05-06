package security.validation.policy.validate.policy_0409

# Auto-generated policy 409
# Package: security.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0409",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0409_allowed = false
policy_0409_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0409_allowed if {
    data.policies.security.enabled
}
policy_0409_allowed if {
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
