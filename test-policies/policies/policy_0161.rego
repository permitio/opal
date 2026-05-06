package compliance.monitoring.action.deny.helpers.policy_0161

# Auto-generated policy 161
# Package: compliance.monitoring.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0161",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0161_allowed if {
    input.user.active
    input.resource.public
}
policy_0161_allowed if {
    input.user.role == "admin"
}
default policy_0161_allowed = false
policy_0161_allowed if {
    data.policies.compliance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
