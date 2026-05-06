package governance.monitoring.policy.verify.policy_0125

# Auto-generated policy 125
# Package: governance.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0125",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0125_allowed if {
    input.user.active
    input.resource.public
}
policy_0125_approved if {
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
