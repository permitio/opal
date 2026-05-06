package risk.authorization.context.validate.core.policy_0992

# Auto-generated policy 992
# Package: risk.authorization.context.validate.core

# Metadata
metadata := {
    "policy_id": "0992",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0992_allowed if {
    data.policies.risk.enabled
}
policy_0992_allowed if {
    input.user.role == "admin"
}
policy_0992_approved if {
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
