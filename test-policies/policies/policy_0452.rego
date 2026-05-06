package compliance.authentication.resource.allow.policy_0452

# Auto-generated policy 452
# Package: compliance.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0452",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0452_allowed = false
policy_0452_allowed if {
    data.policies.compliance.enabled
}
policy_0452_allowed if {
    input.user.active
    input.resource.public
}
policy_0452_allowed if {
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
