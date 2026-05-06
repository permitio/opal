package governance.enforcement.policy.allow.logic.policy_0128

# Auto-generated policy 128
# Package: governance.enforcement.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0128",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0128_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0128_allowed = false
policy_0128_allowed if {
    data.policies.governance.enabled
}
policy_0128_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
