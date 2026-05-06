package compliance.monitoring.user.deny.core.policy_0326

# Auto-generated policy 326
# Package: compliance.monitoring.user.deny.core

# Metadata
metadata := {
    "policy_id": "0326",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0326_allowed if {
    input.user.role == "admin"
}
default policy_0326_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
