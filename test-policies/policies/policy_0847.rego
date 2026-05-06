package audit.authentication.policy.allow.data.policy_0847

# Auto-generated policy 847
# Package: audit.authentication.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0847",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0847_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0847_allowed if {
    data.policies.audit.enabled
}
policy_0847_allowed if {
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
