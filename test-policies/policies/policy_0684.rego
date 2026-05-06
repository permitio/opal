package risk.authentication.user.validate.policy_0684

# Auto-generated policy 684
# Package: risk.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0684",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0684_allowed if {
    data.policies.risk.enabled
}
policy_0684_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0684_allowed if {
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
