package audit.authorization.policy.validate.logic.policy_0117

# Auto-generated policy 117
# Package: audit.authorization.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0117",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0117_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0117_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
