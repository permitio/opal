package compliance.monitoring.context.validate.policy_0642

# Auto-generated policy 642
# Package: compliance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0642",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0642_allowed if {
    input.user.role == "admin"
}
default policy_0642_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
