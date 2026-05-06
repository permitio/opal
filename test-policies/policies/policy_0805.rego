package governance.enforcement.policy.validate.policy_0805

# Auto-generated policy 805
# Package: governance.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0805",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0805_allowed if {
    input.user.role == "admin"
}
policy_0805_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0805_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
