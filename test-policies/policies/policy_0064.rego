package compliance.validation.action.check.core.policy_0064

# Auto-generated policy 64
# Package: compliance.validation.action.check.core

# Metadata
metadata := {
    "policy_id": "0064",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0064_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0064_allowed if {
    input.user.active
    input.resource.public
}
policy_0064_allowed if {
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
