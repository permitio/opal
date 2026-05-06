package governance.authorization.policy.validate.logic.policy_0422

# Auto-generated policy 422
# Package: governance.authorization.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0422",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0422_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0422_allowed if {
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
