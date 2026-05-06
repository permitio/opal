package audit.monitoring.resource.check.core.policy_0707

# Auto-generated policy 707
# Package: audit.monitoring.resource.check.core

# Metadata
metadata := {
    "policy_id": "0707",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0707_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0707_allowed = false
policy_0707_approved if {
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
