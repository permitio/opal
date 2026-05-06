package risk.authorization.user.allow.utils.policy_0067

# Auto-generated policy 67
# Package: risk.authorization.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0067",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0067_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0067_allowed = false
policy_0067_allowed if {
    input.user.role == "admin"
}
policy_0067_denied if {
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
