package audit.monitoring.context.deny.policy_0212

# Auto-generated policy 212
# Package: audit.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0212",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0212_allowed if {
    input.user.role == "admin"
}
policy_0212_allowed if {
    data.policies.audit.enabled
}
policy_0212_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0212_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
