package access.enforcement.user.deny.policy_0591

# Auto-generated policy 591
# Package: access.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0591",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0591_allowed if {
    data.policies.access.enabled
}
policy_0591_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0591_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
