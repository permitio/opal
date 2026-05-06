package compliance.validation.context.check.utils.policy_0026

# Auto-generated policy 26
# Package: compliance.validation.context.check.utils

# Metadata
metadata := {
    "policy_id": "0026",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0026_allowed if {
    input.user.role == "admin"
}
policy_0026_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0026_approved if {
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
