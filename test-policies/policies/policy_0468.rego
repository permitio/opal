package security.monitoring.user.validate.utils.policy_0468

# Auto-generated policy 468
# Package: security.monitoring.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0468",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0468_allowed if {
    input.user.role == "admin"
}
default policy_0468_allowed = false
policy_0468_allowed if {
    data.policies.security.enabled
}
policy_0468_allowed if {
    input.user.active
    input.resource.public
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
