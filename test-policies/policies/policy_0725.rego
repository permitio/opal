package audit.authorization.policy.validate.policy_0725

# Auto-generated policy 725
# Package: audit.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0725",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0725_allowed if {
    input.user.active
    input.resource.public
}
policy_0725_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0725_allowed if {
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
