package audit.monitoring.context.allow.logic.policy_0350

# Auto-generated policy 350
# Package: audit.monitoring.context.allow.logic

# Metadata
metadata := {
    "policy_id": "0350",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0350_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0350_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0350_allowed = false
policy_0350_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
