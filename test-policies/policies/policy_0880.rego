package risk.authorization.context.allow.policy_0880

# Auto-generated policy 880
# Package: risk.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0880",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0880_allowed if {
    input.user.active
    input.resource.public
}
policy_0880_allowed if {
    data.policies.risk.enabled
}
default policy_0880_allowed = false
policy_0880_approved if {
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
