package risk.monitoring.user.check.policy_0406

# Auto-generated policy 406
# Package: risk.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0406",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0406_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0406_allowed = false
policy_0406_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0406_allowed if {
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
