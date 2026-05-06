package compliance.monitoring.resource.verify.data.policy_0553

# Auto-generated policy 553
# Package: compliance.monitoring.resource.verify.data

# Metadata
metadata := {
    "policy_id": "0553",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0553_allowed = false
policy_0553_allowed if {
    data.policies.compliance.enabled
}
policy_0553_allowed if {
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
