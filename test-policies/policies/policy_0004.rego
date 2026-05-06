package governance.validation.resource.validate.policy_0004

# Auto-generated policy 4
# Package: governance.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0004",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0004_allowed if {
    input.user.role == "admin"
}
policy_0004_allowed if {
    data.policies.governance.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
