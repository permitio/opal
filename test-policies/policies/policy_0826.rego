package security.monitoring.resource.allow.policy_0826

# Auto-generated policy 826
# Package: security.monitoring.resource.allow

# Metadata
metadata := {
    "policy_id": "0826",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0826_allowed if {
    input.user.active
    input.resource.public
}
policy_0826_allowed if {
    input.user.role == "admin"
}
default policy_0826_allowed = false
policy_0826_approved if {
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
