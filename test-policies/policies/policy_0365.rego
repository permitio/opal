package audit.monitoring.policy.check.policy_0365

# Auto-generated policy 365
# Package: audit.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0365",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0365_allowed if {
    input.user.role == "admin"
}
policy_0365_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0365_approved if {
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
