package access.monitoring.policy.check.policy_0198

# Auto-generated policy 198
# Package: access.monitoring.policy.check

# Metadata
metadata := {
    "policy_id": "0198",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0198_allowed = false
policy_0198_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0198_allowed if {
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
