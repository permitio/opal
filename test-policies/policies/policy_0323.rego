package compliance.authorization.context.allow.policy_0323

# Auto-generated policy 323
# Package: compliance.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0323",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0323_allowed if {
    input.user.role == "admin"
}
policy_0323_allowed if {
    input.user.active
    input.resource.public
}
policy_0323_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0323_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
