package compliance.monitoring.action.check.data.policy_0427

# Auto-generated policy 427
# Package: compliance.monitoring.action.check.data

# Metadata
metadata := {
    "policy_id": "0427",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0427_allowed = false
policy_0427_allowed if {
    input.user.role == "admin"
}
policy_0427_allowed if {
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
