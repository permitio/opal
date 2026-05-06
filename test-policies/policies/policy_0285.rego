package security.authentication.user.verify.helpers.policy_0285

# Auto-generated policy 285
# Package: security.authentication.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0285",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0285_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0285_allowed = false
policy_0285_allowed if {
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
