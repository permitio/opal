package compliance.validation.user.check.policy_0812

# Auto-generated policy 812
# Package: compliance.validation.user.check

# Metadata
metadata := {
    "policy_id": "0812",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0812_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0812_allowed = false
policy_0812_allowed if {
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
