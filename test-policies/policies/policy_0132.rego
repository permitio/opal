package security.enforcement.action.validate.policy_0132

# Auto-generated policy 132
# Package: security.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0132",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0132_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0132_denied if {
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
