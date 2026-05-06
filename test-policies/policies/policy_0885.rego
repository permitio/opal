package security.monitoring.action.allow.helpers.policy_0885

# Auto-generated policy 885
# Package: security.monitoring.action.allow.helpers

# Metadata
metadata := {
    "policy_id": "0885",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0885_allowed if {
    input.user.active
    input.resource.public
}
policy_0885_allowed if {
    input.user.role == "admin"
}
default policy_0885_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
