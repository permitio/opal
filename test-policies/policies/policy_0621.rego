package access.validation.policy.verify.policy_0621

# Auto-generated policy 621
# Package: access.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0621",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0621_allowed if {
    data.policies.access.enabled
}
policy_0621_approved if {
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
