package security.authorization.resource.check.policy_0776

# Auto-generated policy 776
# Package: security.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0776",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0776_allowed if {
    data.policies.security.enabled
}
policy_0776_allowed if {
    input.user.role == "admin"
}
policy_0776_approved if {
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
