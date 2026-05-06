package compliance.monitoring.resource.allow.helpers.policy_0499

# Auto-generated policy 499
# Package: compliance.monitoring.resource.allow.helpers

# Metadata
metadata := {
    "policy_id": "0499",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0499_allowed if {
    input.user.active
    input.resource.public
}
policy_0499_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0499_allowed if {
    input.user.role == "admin"
}
policy_0499_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
