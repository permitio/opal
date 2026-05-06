package access.monitoring.resource.verify.policy_0083

# Auto-generated policy 83
# Package: access.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0083",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0083_allowed if {
    input.user.active
    input.resource.public
}
policy_0083_allowed if {
    input.user.role == "admin"
}
default policy_0083_allowed = false
policy_0083_approved if {
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
