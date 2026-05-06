package audit.monitoring.action.deny.policy_1000

# Auto-generated policy 1000
# Package: audit.monitoring.action.deny

# Metadata
metadata := {
    "policy_id": "1000",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_1000_allowed if {
    input.user.role == "admin"
}
policy_1000_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_1000_allowed if {
    input.user.active
    input.resource.public
}
policy_1000_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
