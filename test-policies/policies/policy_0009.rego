package audit.authentication.policy.check.policy_0009

# Auto-generated policy 9
# Package: audit.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0009",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0009_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0009_allowed if {
    input.user.role == "admin"
}
default policy_0009_allowed = false
policy_0009_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
