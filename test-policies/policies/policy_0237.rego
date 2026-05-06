package governance.authentication.context.validate.utils.policy_0237

# Auto-generated policy 237
# Package: governance.authentication.context.validate.utils

# Metadata
metadata := {
    "policy_id": "0237",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0237_allowed = false
policy_0237_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0237_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
