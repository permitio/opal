package audit.monitoring.action.deny.helpers.policy_0337

# Auto-generated policy 337
# Package: audit.monitoring.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0337",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0337_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0337_allowed if {
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
