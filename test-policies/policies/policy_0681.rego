package risk.enforcement.action.deny.utils.policy_0681

# Auto-generated policy 681
# Package: risk.enforcement.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0681",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0681_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0681_allowed if {
    data.policies.risk.enabled
}
default policy_0681_allowed = false
policy_0681_approved if {
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
