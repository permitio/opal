package governance.authorization.context.deny.utils.policy_0013

# Auto-generated policy 13
# Package: governance.authorization.context.deny.utils

# Metadata
metadata := {
    "policy_id": "0013",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0013_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0013_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0013_allowed if {
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
