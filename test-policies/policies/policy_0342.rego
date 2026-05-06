package security.enforcement.context.validate.policy_0342

# Auto-generated policy 342
# Package: security.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0342",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0342_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0342_allowed = false
policy_0342_allowed if {
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
