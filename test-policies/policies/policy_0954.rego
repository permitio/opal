package risk.enforcement.policy.allow.policy_0954

# Auto-generated policy 954
# Package: risk.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0954",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0954_allowed if {
    data.policies.risk.enabled
}
policy_0954_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0954_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
