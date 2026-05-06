package security.enforcement.context.check.policy_0461

# Auto-generated policy 461
# Package: security.enforcement.context.check

# Metadata
metadata := {
    "policy_id": "0461",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0461_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0461_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
