package compliance.validation.user.validate.policy_0854

# Auto-generated policy 854
# Package: compliance.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0854",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0854_allowed if {
    input.user.active
    input.resource.public
}
policy_0854_allowed if {
    data.policies.compliance.enabled
}
policy_0854_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
