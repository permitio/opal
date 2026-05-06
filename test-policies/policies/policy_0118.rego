package governance.monitoring.context.check.policy_0118

# Auto-generated policy 118
# Package: governance.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0118",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0118_allowed if {
    input.user.active
    input.resource.public
}
policy_0118_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0118_allowed if {
    data.policies.governance.enabled
}
policy_0118_approved if {
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
