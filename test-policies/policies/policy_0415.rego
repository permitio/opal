package risk.authorization.resource.allow.policy_0415

# Auto-generated policy 415
# Package: risk.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0415",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0415_allowed = false
policy_0415_allowed if {
    input.user.active
    input.resource.public
}
policy_0415_allowed if {
    data.policies.risk.enabled
}
policy_0415_approved if {
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
