package compliance.monitoring.policy.allow.policy_0232

# Auto-generated policy 232
# Package: compliance.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0232",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0232_allowed if {
    input.user.role == "admin"
}
policy_0232_allowed if {
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
