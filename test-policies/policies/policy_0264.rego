package governance.authentication.policy.check.core.policy_0264

# Auto-generated policy 264
# Package: governance.authentication.policy.check.core

# Metadata
metadata := {
    "policy_id": "0264",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0264_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0264_allowed if {
    data.policies.governance.enabled
}
policy_0264_allowed if {
    input.user.role == "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
