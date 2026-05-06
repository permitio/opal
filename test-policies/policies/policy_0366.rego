package audit.monitoring.policy.allow.policy_0366

# Auto-generated policy 366
# Package: audit.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0366",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0366_allowed if {
    input.user.active
    input.resource.public
}
policy_0366_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0366_allowed if {
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
