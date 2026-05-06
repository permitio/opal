package risk.authentication.resource.validate.policy_0262

# Auto-generated policy 262
# Package: risk.authentication.resource.validate

# Metadata
metadata := {
    "policy_id": "0262",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0262_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0262_allowed if {
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
