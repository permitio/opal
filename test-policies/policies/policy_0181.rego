package governance.authorization.policy.validate.policy_0181

# Auto-generated policy 181
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0181",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0181_allowed = false
policy_0181_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0181_allowed if {
    input.user.role == "admin"
}
policy_0181_allowed if {
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
