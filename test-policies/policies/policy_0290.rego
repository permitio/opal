package security.enforcement.policy.validate.policy_0290

# Auto-generated policy 290
# Package: security.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0290",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0290_allowed if {
    data.policies.security.enabled
}
default policy_0290_allowed = false
policy_0290_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0290_denied if {
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
