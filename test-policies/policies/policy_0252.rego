package compliance.monitoring.resource.validate.policy_0252

# Auto-generated policy 252
# Package: compliance.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0252",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0252_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0252_allowed if {
    input.user.active
    input.resource.public
}
default policy_0252_allowed = false
policy_0252_allowed if {
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
