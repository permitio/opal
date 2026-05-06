package security.monitoring.action.verify.policy_0450

# Auto-generated policy 450
# Package: security.monitoring.action.verify

# Metadata
metadata := {
    "policy_id": "0450",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0450_allowed if {
    input.user.active
    input.resource.public
}
policy_0450_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0450_denied if {
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
