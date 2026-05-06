package access.authorization.action.allow.data.policy_0098

# Auto-generated policy 98
# Package: access.authorization.action.allow.data

# Metadata
metadata := {
    "policy_id": "0098",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0098_allowed if {
    input.user.role == "admin"
}
policy_0098_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0098_allowed if {
    input.user.active
    input.resource.public
}
default policy_0098_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
