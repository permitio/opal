package audit.validation.action.check.policy_0352

# Auto-generated policy 352
# Package: audit.validation.action.check

# Metadata
metadata := {
    "policy_id": "0352",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0352_allowed = false
policy_0352_allowed if {
    data.policies.audit.enabled
}
policy_0352_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0352_allowed if {
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
