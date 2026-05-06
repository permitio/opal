package compliance.authorization.resource.verify.policy_0864

# Auto-generated policy 864
# Package: compliance.authorization.resource.verify

# Metadata
metadata := {
    "policy_id": "0864",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0864_allowed if {
    data.policies.compliance.enabled
}
policy_0864_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0864_allowed if {
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
