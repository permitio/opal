package access.authentication.user.deny.policy_0234

# Auto-generated policy 234
# Package: access.authentication.user.deny

# Metadata
metadata := {
    "policy_id": "0234",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0234_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0234_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0234_allowed if {
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
