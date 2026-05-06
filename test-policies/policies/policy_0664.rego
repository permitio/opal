package access.authorization.policy.allow.core.policy_0664

# Auto-generated policy 664
# Package: access.authorization.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0664",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0664_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0664_allowed = false
policy_0664_allowed if {
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
