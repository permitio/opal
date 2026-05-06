package risk.authorization.policy.validate.data.policy_0377

# Auto-generated policy 377
# Package: risk.authorization.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0377",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0377_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0377_allowed = false
policy_0377_allowed if {
    input.user.role == "admin"
}
policy_0377_approved if {
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
