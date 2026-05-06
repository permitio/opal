package access.enforcement.context.deny.policy_0822

# Auto-generated policy 822
# Package: access.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0822",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0822_allowed if {
    input.user.active
    input.resource.public
}
policy_0822_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0822_allowed if {
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
