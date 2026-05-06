package compliance.authorization.action.check.utils.policy_0229

# Auto-generated policy 229
# Package: compliance.authorization.action.check.utils

# Metadata
metadata := {
    "policy_id": "0229",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0229_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0229_allowed if {
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
