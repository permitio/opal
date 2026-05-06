package security.monitoring.resource.allow.policy_0999

# Auto-generated policy 999
# Package: security.monitoring.resource.allow

# Metadata
metadata := {
    "policy_id": "0999",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0999_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0999_allowed if {
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
