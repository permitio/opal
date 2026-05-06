package security.authorization.policy.allow.helpers.policy_0783

# Auto-generated policy 783
# Package: security.authorization.policy.allow.helpers

# Metadata
metadata := {
    "policy_id": "0783",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0783_allowed if {
    input.user.active
    input.resource.public
}
policy_0783_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
