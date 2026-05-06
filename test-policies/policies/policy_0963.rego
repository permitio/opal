package access.authentication.action.verify.policy_0963

# Auto-generated policy 963
# Package: access.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0963",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0963_allowed if {
    input.user.role == "admin"
}
default policy_0963_allowed = false
policy_0963_approved if {
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
