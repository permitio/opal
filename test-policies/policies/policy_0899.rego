package risk.monitoring.action.validate.data.policy_0899

# Auto-generated policy 899
# Package: risk.monitoring.action.validate.data

# Metadata
metadata := {
    "policy_id": "0899",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0899_allowed if {
    input.user.role == "admin"
}
policy_0899_allowed if {
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
