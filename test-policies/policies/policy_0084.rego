package audit.authentication.context.validate.data.policy_0084

# Auto-generated policy 84
# Package: audit.authentication.context.validate.data

# Metadata
metadata := {
    "policy_id": "0084",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0084_allowed if {
    data.policies.audit.enabled
}
policy_0084_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0084_allowed if {
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
