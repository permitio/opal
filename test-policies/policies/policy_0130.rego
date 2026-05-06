package audit.authorization.action.deny.data.policy_0130

# Auto-generated policy 130
# Package: audit.authorization.action.deny.data

# Metadata
metadata := {
    "policy_id": "0130",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0130_allowed if {
    data.policies.audit.enabled
}
policy_0130_allowed if {
    input.user.role == "admin"
}
policy_0130_approved if {
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
