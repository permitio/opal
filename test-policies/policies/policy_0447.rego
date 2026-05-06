package audit.monitoring.resource.validate.policy_0447

# Auto-generated policy 447
# Package: audit.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0447",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0447_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0447_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0447_allowed if {
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
