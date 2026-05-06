package audit.monitoring.action.check.policy_0187

# Auto-generated policy 187
# Package: audit.monitoring.action.check

# Metadata
metadata := {
    "policy_id": "0187",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0187_allowed if {
    input.user.role == "admin"
}
policy_0187_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0187_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0187_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
