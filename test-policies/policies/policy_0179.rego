package access.authorization.action.validate.policy_0179

# Auto-generated policy 179
# Package: access.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0179",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0179_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0179_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
