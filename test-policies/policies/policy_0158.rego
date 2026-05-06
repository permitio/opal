package governance.enforcement.context.deny.policy_0158

# Auto-generated policy 158
# Package: governance.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0158",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0158_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0158_allowed if {
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
