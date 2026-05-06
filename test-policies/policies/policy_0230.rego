package governance.authorization.policy.validate.policy_0230

# Auto-generated policy 230
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0230",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0230_allowed if {
    data.policies.governance.enabled
}
policy_0230_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0230_allowed if {
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
