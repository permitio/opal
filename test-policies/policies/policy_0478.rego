package compliance.authorization.resource.allow.policy_0478

# Auto-generated policy 478
# Package: compliance.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0478",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0478_allowed = false
policy_0478_allowed if {
    input.user.role == "admin"
}
policy_0478_allowed if {
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
