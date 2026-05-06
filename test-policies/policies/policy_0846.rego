package governance.validation.resource.validate.policy_0846

# Auto-generated policy 846
# Package: governance.validation.resource.validate

# Metadata
metadata := {
    "policy_id": "0846",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0846_allowed if {
    data.policies.governance.enabled
}
policy_0846_allowed if {
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
