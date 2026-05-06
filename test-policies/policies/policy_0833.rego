package risk.validation.context.validate.policy_0833

# Auto-generated policy 833
# Package: risk.validation.context.validate

# Metadata
metadata := {
    "policy_id": "0833",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0833_allowed = false
policy_0833_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0833_allowed if {
    input.user.role == "admin"
}
policy_0833_approved if {
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
