package compliance.enforcement.policy.verify.policy_0088

# Auto-generated policy 88
# Package: compliance.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0088",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0088_allowed if {
    input.user.role == "admin"
}
policy_0088_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0088_allowed if {
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
