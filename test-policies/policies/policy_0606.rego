package compliance.monitoring.user.verify.policy_0606

# Auto-generated policy 606
# Package: compliance.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0606",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0606_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0606_allowed if {
    data.policies.compliance.enabled
}
policy_0606_allowed if {
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
