package risk.enforcement.action.deny.policy_0563

# Auto-generated policy 563
# Package: risk.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0563",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0563_allowed if {
    data.policies.risk.enabled
}
policy_0563_approved if {
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
