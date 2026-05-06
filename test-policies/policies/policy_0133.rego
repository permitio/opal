package compliance.authorization.action.allow.policy_0133

# Auto-generated policy 133
# Package: compliance.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0133",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0133_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0133_allowed if {
    data.policies.compliance.enabled
}
policy_0133_allowed if {
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
