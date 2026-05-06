package audit.monitoring.policy.check.policy_0214

# Auto-generated policy 214
# Package: audit.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0214",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0214_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0214_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0214_allowed if {
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
