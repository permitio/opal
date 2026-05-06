package audit.monitoring.policy.deny.policy_0034

# Auto-generated policy 34
# Package: audit.monitoring.policy.deny

# Metadata
metadata := {
    "policy_id": "0034",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0034_allowed if {
    input.user.active
    input.resource.public
}
policy_0034_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
