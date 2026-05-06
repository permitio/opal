package access.validation.action.check.core.policy_0408

# Auto-generated policy 408
# Package: access.validation.action.check.core

# Metadata
metadata := {
    "policy_id": "0408",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0408_allowed = false
policy_0408_allowed if {
    input.user.role == "admin"
}
policy_0408_approved if {
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
