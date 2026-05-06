package compliance.monitoring.action.verify.policy_0120

# Auto-generated policy 120
# Package: compliance.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0120",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0120_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0120_allowed if {
    input.user.active
    input.resource.public
}
default policy_0120_allowed = false
policy_0120_allowed if {
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
