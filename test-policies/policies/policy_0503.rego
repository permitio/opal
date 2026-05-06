package audit.monitoring.context.check.policy_0503

# Auto-generated policy 503
# Package: audit.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0503",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0503_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0503_allowed = false
policy_0503_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0503_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
