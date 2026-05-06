package security.authorization.resource.validate.policy_0685

# Auto-generated policy 685
# Package: security.authorization.resource.validate

# Metadata
metadata := {
    "policy_id": "0685",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0685_allowed if {
    data.policies.security.enabled
}
policy_0685_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0685_allowed = false
policy_0685_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
