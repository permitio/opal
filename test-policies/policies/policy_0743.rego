package governance.monitoring.user.check.logic.policy_0743

# Auto-generated policy 743
# Package: governance.monitoring.user.check.logic

# Metadata
metadata := {
    "policy_id": "0743",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0743_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0743_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0743_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
