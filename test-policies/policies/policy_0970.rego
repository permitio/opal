package security.authentication.action.validate.utils.policy_0970

# Auto-generated policy 970
# Package: security.authentication.action.validate.utils

# Metadata
metadata := {
    "policy_id": "0970",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0970_allowed if {
    data.policies.security.enabled
}
policy_0970_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0970_approved if {
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
