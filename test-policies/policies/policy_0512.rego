package access.validation.action.check.policy_0512

# Auto-generated policy 512
# Package: access.validation.action.check

# Metadata
metadata := {
    "policy_id": "0512",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0512_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0512_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
