package governance.validation.policy.verify.policy_0994

# Auto-generated policy 994
# Package: governance.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0994",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0994_allowed if {
    input.user.role == "admin"
}
policy_0994_allowed if {
    data.policies.governance.enabled
}
default policy_0994_allowed = false
policy_0994_allowed if {
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
