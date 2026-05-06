package access.monitoring.action.deny.policy_0628

# Auto-generated policy 628
# Package: access.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "0628",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0628_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0628_allowed if {
    input.user.active
    input.resource.public
}
policy_0628_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0628_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
