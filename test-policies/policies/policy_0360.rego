package governance.validation.resource.validate.policy_0360

# Auto-generated policy 360
# Package: governance.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0360",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0360_allowed = false
policy_0360_allowed if {
    data.policies.governance.enabled
}
policy_0360_approved if {
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
