package governance.authorization.user.validate.policy_0835

# Auto-generated policy 835
# Package: governance.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0835",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0835_allowed = false
policy_0835_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0835_allowed if {
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
