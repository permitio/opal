package governance.monitoring.resource.check.logic.policy_0537

# Auto-generated policy 537
# Package: governance.monitoring.resource.check.logic

# Metadata
metadata := {
    "policy_id": "0537",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0537_allowed if {
    input.user.active
    input.resource.public
}
policy_0537_allowed if {
    input.user.role == "admin"
}
policy_0537_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0537_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
