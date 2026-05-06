package security.validation.policy.deny.policy_0123

# Auto-generated policy 123
# Package: security.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0123",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0123_allowed = false
policy_0123_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0123_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
