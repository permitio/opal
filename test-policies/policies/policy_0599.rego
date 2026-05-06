package compliance.authorization.user.validate.policy_0599

# Auto-generated policy 599
# Package: compliance.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0599",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0599_allowed if {
    input.user.role == "admin"
}
policy_0599_allowed if {
    input.user.active
    input.resource.public
}
policy_0599_allowed if {
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
