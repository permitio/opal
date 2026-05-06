package security.authorization.policy.validate.policy_0355

# Auto-generated policy 355
# Package: security.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0355",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0355_allowed = false
policy_0355_allowed if {
    input.user.role == "admin"
}
policy_0355_allowed if {
    input.user.active
    input.resource.public
}
policy_0355_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
