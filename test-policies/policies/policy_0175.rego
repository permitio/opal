package audit.authorization.user.allow.policy_0175

# Auto-generated policy 175
# Package: audit.authorization.user.allow

# Metadata
metadata := {
    "policy_id": "0175",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0175_allowed if {
    input.user.role == "admin"
}
policy_0175_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0175_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
