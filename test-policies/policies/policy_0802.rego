package security.validation.action.deny.policy_0802

# Auto-generated policy 802
# Package: security.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0802",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0802_allowed if {
    data.policies.security.enabled
}
default policy_0802_allowed = false
policy_0802_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0802_denied if {
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
