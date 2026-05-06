package security.monitoring.action.validate.policy_0387

# Auto-generated policy 387
# Package: security.monitoring.action.validate

# Metadata
metadata := {
    "policy_id": "0387",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0387_allowed if {
    input.user.role == "admin"
}
default policy_0387_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
