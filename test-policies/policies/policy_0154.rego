package security.authentication.context.validate.policy_0154

# Auto-generated policy 154
# Package: security.authentication.context.validate

# Metadata
metadata := {
    "policy_id": "0154",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0154_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0154_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0154_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
