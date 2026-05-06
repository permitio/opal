package security.monitoring.resource.validate.policy_0895

# Auto-generated policy 895
# Package: security.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0895",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0895_allowed if {
    input.user.role == "admin"
}
policy_0895_allowed if {
    input.user.active
    input.resource.public
}
policy_0895_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0895_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
