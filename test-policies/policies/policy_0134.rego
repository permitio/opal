package audit.authorization.policy.deny.policy_0134

# Auto-generated policy 134
# Package: audit.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0134",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0134_allowed if {
    input.user.active
    input.resource.public
}
policy_0134_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0134_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
