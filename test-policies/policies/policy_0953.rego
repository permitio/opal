package compliance.authorization.policy.deny.core.policy_0953

# Auto-generated policy 953
# Package: compliance.authorization.policy.deny.core

# Metadata
metadata := {
    "policy_id": "0953",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0953_allowed if {
    input.user.active
    input.resource.public
}
policy_0953_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0953_denied if {
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
