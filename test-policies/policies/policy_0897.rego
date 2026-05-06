package risk.authorization.user.validate.policy_0897

# Auto-generated policy 897
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0897",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0897_allowed if {
    input.user.role == "admin"
}
policy_0897_allowed if {
    data.policies.risk.enabled
}
policy_0897_approved if {
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
