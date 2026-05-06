package compliance.monitoring.action.validate.policy_0784

# Auto-generated policy 784
# Package: compliance.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0784",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0784_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0784_allowed if {
    data.policies.compliance.enabled
}
policy_0784_allowed if {
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
