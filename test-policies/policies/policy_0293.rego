package audit.validation.context.allow.policy_0293

# Auto-generated policy 293
# Package: audit.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0293",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0293_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0293_allowed if {
    data.policies.audit.enabled
}
policy_0293_allowed if {
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
