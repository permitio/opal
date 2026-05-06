package compliance.enforcement.policy.verify.utils.policy_0907

# Auto-generated policy 907
# Package: compliance.enforcement.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0907",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0907_allowed = false
policy_0907_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0907_allowed if {
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
