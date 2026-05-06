package compliance.monitoring.context.deny.policy_0887

# Auto-generated policy 887
# Package: compliance.monitoring.context.deny

# Metadata
metadata := {
    "policy_id": "0887",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0887_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0887_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0887_allowed if {
    data.policies.compliance.enabled
}
policy_0887_allowed if {
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
