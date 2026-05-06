package risk.enforcement.action.allow.policy_0798

# Auto-generated policy 798
# Package: risk.enforcement.action.allow

# Metadata
metadata := {
    "policy_id": "0798",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0798_allowed = false
policy_0798_allowed if {
    input.user.role == "admin"
}
policy_0798_allowed if {
    data.policies.risk.enabled
}
policy_0798_approved if {
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
