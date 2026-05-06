package access.authorization.policy.deny.policy_0636

# Auto-generated policy 636
# Package: access.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0636",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0636_allowed if {
    input.user.role == "admin"
}
policy_0636_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0636_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
