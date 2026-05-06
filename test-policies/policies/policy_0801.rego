package compliance.monitoring.user.deny.policy_0801

# Auto-generated policy 801
# Package: compliance.monitoring.user.deny

# Metadata
metadata := {
    "policy_id": "0801",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0801_allowed if {
    input.user.role == "admin"
}
policy_0801_allowed if {
    input.user.active
    input.resource.public
}
policy_0801_allowed if {
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
