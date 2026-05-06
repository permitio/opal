package risk.monitoring.policy.deny.helpers.policy_0192

# Auto-generated policy 192
# Package: risk.monitoring.policy.deny.helpers

# Metadata
metadata := {
    "policy_id": "0192",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0192_allowed if {
    input.user.active
    input.resource.public
}
default policy_0192_allowed = false
policy_0192_allowed if {
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
