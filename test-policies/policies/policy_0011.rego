package security.monitoring.policy.check.policy_0011

# Auto-generated policy 11
# Package: security.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0011",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0011_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0011_allowed if {
    input.user.role == "admin"
}
policy_0011_allowed if {
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
