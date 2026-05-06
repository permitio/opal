package governance.authorization.policy.verify.policy_0121

# Auto-generated policy 121
# Package: governance.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0121",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0121_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0121_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0121_allowed if {
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
