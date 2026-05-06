package access.authorization.resource.verify.policy_0358

# Auto-generated policy 358
# Package: access.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0358",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0358_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0358_allowed if {
    input.user.active
    input.resource.public
}
policy_0358_allowed if {
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
