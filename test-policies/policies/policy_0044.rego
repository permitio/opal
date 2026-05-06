package access.authentication.context.validate.policy_0044

# Auto-generated policy 44
# Package: access.authentication.context.validate

# Metadata
metadata := {
    "policy_id": "0044",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0044_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0044_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
