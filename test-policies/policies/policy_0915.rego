package audit.monitoring.resource.deny.data.policy_0915

# Auto-generated policy 915
# Package: audit.monitoring.resource.deny.data

# Metadata
metadata := {
    "policy_id": "0915",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0915_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0915_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0915_allowed = false
policy_0915_allowed if {
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
