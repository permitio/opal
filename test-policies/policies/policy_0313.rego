package security.monitoring.user.deny.policy_0313

# Auto-generated policy 313
# Package: security.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0313",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0313_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0313_denied if {
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
