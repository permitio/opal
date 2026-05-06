package governance.enforcement.action.deny.policy_0827

# Auto-generated policy 827
# Package: governance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0827",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0827_allowed if {
    data.policies.governance.enabled
}
policy_0827_allowed if {
    input.user.role == "admin"
}
policy_0827_approved if {
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
