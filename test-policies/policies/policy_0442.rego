package governance.enforcement.resource.allow.policy_0442

# Auto-generated policy 442
# Package: governance.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0442",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0442_allowed if {
    data.policies.governance.enabled
}
policy_0442_allowed if {
    input.user.active
    input.resource.public
}
policy_0442_approved if {
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
