package risk.authorization.action.allow.policy_0943

# Auto-generated policy 943
# Package: risk.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0943",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0943_allowed if {
    input.user.active
    input.resource.public
}
policy_0943_allowed if {
    input.user.role == "admin"
}
policy_0943_approved if {
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
