package risk.monitoring.policy.allow.policy_0061

# Auto-generated policy 61
# Package: risk.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0061",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0061_allowed if {
    input.user.active
    input.resource.public
}
policy_0061_allowed if {
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
