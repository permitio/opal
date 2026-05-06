package governance.authorization.policy.check.utils.policy_0085

# Auto-generated policy 85
# Package: governance.authorization.policy.check.utils

# Metadata
metadata := {
    "policy_id": "0085",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0085_allowed = false
policy_0085_allowed if {
    input.user.role == "admin"
}
policy_0085_allowed if {
    input.user.active
    input.resource.public
}
policy_0085_approved if {
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
