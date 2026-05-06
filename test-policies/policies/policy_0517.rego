package access.monitoring.action.allow.logic.policy_0517

# Auto-generated policy 517
# Package: access.monitoring.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0517",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0517_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0517_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0517_allowed if {
    input.user.active
    input.resource.public
}
default policy_0517_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
