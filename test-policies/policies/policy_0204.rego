package governance.monitoring.user.allow.policy_0204

# Auto-generated policy 204
# Package: governance.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0204",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0204_allowed if {
    input.user.role == "admin"
}
policy_0204_allowed if {
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
