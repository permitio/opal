package audit.authorization.user.validate.core.policy_0966

# Auto-generated policy 966
# Package: audit.authorization.user.validate.core

# Metadata
metadata := {
    "policy_id": "0966",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0966_allowed if {
    input.user.role == "admin"
}
policy_0966_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0966_allowed if {
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
