package security.authentication.resource.deny.core.policy_0109

# Auto-generated policy 109
# Package: security.authentication.resource.deny.core

# Metadata
metadata := {
    "policy_id": "0109",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0109_allowed if {
    data.policies.security.enabled
}
policy_0109_approved if {
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
