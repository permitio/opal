package audit.authentication.action.allow.policy_0426

# Auto-generated policy 426
# Package: audit.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0426",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0426_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0426_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
