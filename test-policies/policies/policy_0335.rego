package security.authentication.action.validate.utils.policy_0335

# Auto-generated policy 335
# Package: security.authentication.action.validate.utils

# Metadata
metadata := {
    "policy_id": "0335",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0335_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0335_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
