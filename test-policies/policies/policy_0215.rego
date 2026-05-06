package access.enforcement.policy.check.core.policy_0215

# Auto-generated policy 215
# Package: access.enforcement.policy.check.core

# Metadata
metadata := {
    "policy_id": "0215",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0215_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0215_allowed = false
policy_0215_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0215_allowed if {
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
