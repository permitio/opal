package governance.monitoring.context.validate.policy_0196

# Auto-generated policy 196
# Package: governance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0196",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0196_allowed if {
    input.user.role == "admin"
}
policy_0196_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0196_allowed if {
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
