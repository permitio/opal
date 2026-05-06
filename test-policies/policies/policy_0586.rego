package compliance.monitoring.user.validate.policy_0586

# Auto-generated policy 586
# Package: compliance.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0586",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0586_allowed if {
    data.policies.compliance.enabled
}
policy_0586_allowed if {
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
