package security.authentication.context.allow.helpers.policy_0595

# Auto-generated policy 595
# Package: security.authentication.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0595",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0595_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0595_allowed if {
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
