package access.monitoring.user.check.helpers.policy_0998

# Auto-generated policy 998
# Package: access.monitoring.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0998",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0998_allowed if {
    input.user.role == "admin"
}
default policy_0998_allowed = false
policy_0998_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
