package governance.authorization.policy.allow.policy_0631

# Auto-generated policy 631
# Package: governance.authorization.policy.allow

# Metadata
metadata := {
    "policy_id": "0631",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0631_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0631_allowed if {
    data.policies.governance.enabled
}
policy_0631_allowed if {
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
