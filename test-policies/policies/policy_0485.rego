package access.monitoring.resource.allow.utils.policy_0485

# Auto-generated policy 485
# Package: access.monitoring.resource.allow.utils

# Metadata
metadata := {
    "policy_id": "0485",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0485_allowed if {
    input.user.role == "admin"
}
policy_0485_allowed if {
    input.user.active
    input.resource.public
}
policy_0485_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0485_denied if {
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
