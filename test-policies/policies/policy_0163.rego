package access.enforcement.action.verify.policy_0163

# Auto-generated policy 163
# Package: access.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0163",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0163_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0163_allowed if {
    input.user.active
    input.resource.public
}
policy_0163_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
