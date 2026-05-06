package compliance.validation.action.verify.data.policy_0216

# Auto-generated policy 216
# Package: compliance.validation.action.verify.data

# Metadata
metadata := {
    "policy_id": "0216",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0216_allowed if {
    input.user.active
    input.resource.public
}
policy_0216_allowed if {
    data.policies.compliance.enabled
}
policy_0216_allowed if {
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
