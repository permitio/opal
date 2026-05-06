package security.enforcement.action.deny.core.policy_0110

# Auto-generated policy 110
# Package: security.enforcement.action.deny.core

# Metadata
metadata := {
    "policy_id": "0110",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0110_allowed if {
    data.policies.security.enabled
}
policy_0110_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0110_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
