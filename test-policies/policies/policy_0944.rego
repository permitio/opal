package governance.authorization.context.check.policy_0944

# Auto-generated policy 944
# Package: governance.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0944",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0944_allowed if {
    data.policies.governance.enabled
}
policy_0944_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0944_allowed if {
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
