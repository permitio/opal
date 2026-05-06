package compliance.authentication.policy.allow.helpers.policy_0248

# Auto-generated policy 248
# Package: compliance.authentication.policy.allow.helpers

# Metadata
metadata := {
    "policy_id": "0248",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0248_allowed if {
    data.policies.compliance.enabled
}
policy_0248_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0248_allowed if {
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
