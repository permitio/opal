package governance.enforcement.policy.allow.policy_0491

# Auto-generated policy 491
# Package: governance.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0491",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0491_allowed if {
    data.policies.governance.enabled
}
default policy_0491_allowed = false
policy_0491_allowed if {
    input.user.role == "admin"
}
policy_0491_approved if {
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
