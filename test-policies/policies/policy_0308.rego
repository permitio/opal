package compliance.authorization.action.verify.policy_0308

# Auto-generated policy 308
# Package: compliance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0308",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0308_allowed if {
    data.policies.compliance.enabled
}
default policy_0308_allowed = false
policy_0308_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0308_allowed if {
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
