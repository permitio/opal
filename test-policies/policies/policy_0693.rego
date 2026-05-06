package audit.monitoring.policy.deny.policy_0693

# Auto-generated policy 693
# Package: audit.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0693",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0693_allowed = false
policy_0693_allowed if {
    data.policies.audit.enabled
}
policy_0693_allowed if {
    input.user.role == "admin"
}
policy_0693_approved if {
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
