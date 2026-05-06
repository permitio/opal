package security.validation.action.allow.policy_0836

# Auto-generated policy 836
# Package: security.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0836",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0836_allowed = false
policy_0836_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0836_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0836_allowed if {
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
