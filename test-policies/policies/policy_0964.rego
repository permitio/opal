package audit.authentication.user.deny.policy_0964

# Auto-generated policy 964
# Package: audit.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0964",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0964_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0964_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0964_allowed if {
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
