package governance.monitoring.policy.deny.policy_0709

# Auto-generated policy 709
# Package: governance.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0709",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0709_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0709_allowed if {
    data.policies.governance.enabled
}
policy_0709_allowed if {
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
