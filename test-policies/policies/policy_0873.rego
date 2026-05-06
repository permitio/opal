package compliance.monitoring.policy.deny.policy_0873

# Auto-generated policy 873
# Package: compliance.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0873",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0873_allowed if {
    input.user.active
    input.resource.public
}
policy_0873_allowed if {
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
