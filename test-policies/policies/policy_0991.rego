package risk.authorization.context.verify.policy_0991

# Auto-generated policy 991
# Package: risk.authorization.context.verify

# Metadata
metadata := {
    "policy_id": "0991",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0991_allowed if {
    data.policies.risk.enabled
}
policy_0991_allowed if {
    input.user.role == "admin"
}
policy_0991_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0991_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
