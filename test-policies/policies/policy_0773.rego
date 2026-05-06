package compliance.monitoring.context.allow.policy_0773

# Auto-generated policy 773
# Package: compliance.monitoring.context.allow

# Metadata
metadata := {
    "policy_id": "0773",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0773_allowed if {
    input.user.role == "admin"
}
default policy_0773_allowed = false
policy_0773_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0773_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
