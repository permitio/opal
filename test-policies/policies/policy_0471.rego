package governance.enforcement.policy.check.policy_0471

# Auto-generated policy 471
# Package: governance.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0471",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0471_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0471_allowed if {
    input.user.active
    input.resource.public
}
policy_0471_allowed if {
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
