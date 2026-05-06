package risk.authentication.action.verify.core.policy_0691

# Auto-generated policy 691
# Package: risk.authentication.action.verify.core

# Metadata
metadata := {
    "policy_id": "0691",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0691_allowed if {
    input.user.role == "admin"
}
policy_0691_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0691_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0691_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
