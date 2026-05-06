package audit.monitoring.resource.deny.policy_0070

# Auto-generated policy 70
# Package: audit.monitoring.resource.deny

# Metadata
metadata := {
    "policy_id": "0070",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0070_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0070_allowed if {
    data.policies.audit.enabled
}
policy_0070_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0070_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
