package compliance.authentication.action.verify.policy_0367

# Auto-generated policy 367
# Package: compliance.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0367",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0367_allowed if {
    data.policies.compliance.enabled
}
policy_0367_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0367_allowed = false
policy_0367_allowed if {
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
