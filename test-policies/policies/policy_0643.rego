package risk.authorization.user.validate.policy_0643

# Auto-generated policy 643
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0643",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0643_allowed if {
    data.policies.risk.enabled
}
default policy_0643_allowed = false
policy_0643_allowed if {
    input.user.active
    input.resource.public
}
policy_0643_approved if {
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
