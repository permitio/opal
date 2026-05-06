package risk.monitoring.action.validate.policy_0683

# Auto-generated policy 683
# Package: risk.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0683",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0683_allowed = false
policy_0683_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0683_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0683_allowed if {
    data.policies.risk.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
