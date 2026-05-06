package audit.authorization.context.allow.policy_0153

# Auto-generated policy 153
# Package: audit.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0153",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0153_allowed if {
    input.user.role == "admin"
}
policy_0153_allowed if {
    input.user.active
    input.resource.public
}
policy_0153_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0153_allowed if {
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
