package governance.monitoring.user.deny.policy_0584

# Auto-generated policy 584
# Package: governance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0584",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0584_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0584_allowed if {
    input.user.role == "admin"
}
policy_0584_allowed if {
    input.user.active
    input.resource.public
}
policy_0584_allowed if {
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
