package governance.authentication.policy.validate.utils.policy_0536

# Auto-generated policy 536
# Package: governance.authentication.policy.validate.utils

# Metadata
metadata := {
    "policy_id": "0536",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0536_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0536_allowed if {
    data.policies.governance.enabled
}
default policy_0536_allowed = false
policy_0536_approved if {
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
