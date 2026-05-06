package risk.authorization.action.verify.core.policy_0458

# Auto-generated policy 458
# Package: risk.authorization.action.verify.core

# Metadata
metadata := {
    "policy_id": "0458",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0458_allowed if {
    data.policies.risk.enabled
}
policy_0458_approved if {
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
