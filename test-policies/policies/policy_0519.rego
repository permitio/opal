package governance.enforcement.context.allow.policy_0519

# Auto-generated policy 519
# Package: governance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0519",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0519_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0519_allowed if {
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
