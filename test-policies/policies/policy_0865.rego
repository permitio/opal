package governance.validation.action.check.helpers.policy_0865

# Auto-generated policy 865
# Package: governance.validation.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0865",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0865_allowed if {
    input.user.active
    input.resource.public
}
default policy_0865_allowed = false
policy_0865_allowed if {
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
