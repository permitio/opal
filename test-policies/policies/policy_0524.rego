package compliance.enforcement.policy.deny.policy_0524

# Auto-generated policy 524
# Package: compliance.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0524",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0524_allowed if {
    input.user.active
    input.resource.public
}
policy_0524_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0524_allowed = false
policy_0524_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
