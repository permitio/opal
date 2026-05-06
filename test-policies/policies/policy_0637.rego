package compliance.authorization.action.verify.policy_0637

# Auto-generated policy 637
# Package: compliance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0637",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0637_allowed = false
policy_0637_allowed if {
    input.user.role == "admin"
}
policy_0637_allowed if {
    data.policies.compliance.enabled
}
policy_0637_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
