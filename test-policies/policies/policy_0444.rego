package governance.monitoring.user.deny.data.policy_0444

# Auto-generated policy 444
# Package: governance.monitoring.user.deny.data

# Metadata
metadata := {
    "policy_id": "0444",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0444_allowed if {
    data.policies.governance.enabled
}
default policy_0444_allowed = false
policy_0444_allowed if {
    input.user.active
    input.resource.public
}
policy_0444_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
