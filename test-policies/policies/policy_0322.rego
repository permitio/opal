package security.authorization.action.verify.data.policy_0322

# Auto-generated policy 322
# Package: security.authorization.action.verify.data

# Metadata
metadata := {
    "policy_id": "0322",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0322_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0322_allowed if {
    data.policies.security.enabled
}
policy_0322_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0322_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
