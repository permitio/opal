package governance.validation.user.allow.helpers.policy_0037

# Auto-generated policy 37
# Package: governance.validation.user.allow.helpers

# Metadata
metadata := {
    "policy_id": "0037",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0037_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0037_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
