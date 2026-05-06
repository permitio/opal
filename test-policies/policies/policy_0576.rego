package audit.monitoring.user.deny.policy_0576

# Auto-generated policy 576
# Package: audit.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0576",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0576_allowed if {
    input.user.active
    input.resource.public
}
policy_0576_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0576_allowed if {
    input.user.role == "admin"
}
policy_0576_allowed if {
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
