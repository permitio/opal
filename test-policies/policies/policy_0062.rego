package compliance.validation.user.deny.policy_0062

# Auto-generated policy 62
# Package: compliance.validation.user.deny

# Metadata
metadata := {
    "policy_id": "0062",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0062_allowed = false
policy_0062_approved if {
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
