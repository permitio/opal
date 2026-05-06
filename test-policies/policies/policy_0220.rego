package governance.validation.user.check.policy_0220

# Auto-generated policy 220
# Package: governance.validation.user.check

# Metadata
metadata := {
    "policy_id": "0220",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0220_allowed if {
    input.user.active
    input.resource.public
}
policy_0220_allowed if {
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
