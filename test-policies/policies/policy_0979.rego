package audit.authentication.action.deny.policy_0979

# Auto-generated policy 979
# Package: audit.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0979",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0979_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0979_denied if {
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
