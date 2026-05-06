package compliance.monitoring.policy.check.helpers.policy_0858

# Auto-generated policy 858
# Package: compliance.monitoring.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0858",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0858_allowed = false
policy_0858_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0858_allowed if {
    input.user.active
    input.resource.public
}
policy_0858_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
