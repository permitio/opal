package security.validation.policy.verify.policy_0597

# Auto-generated policy 597
# Package: security.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0597",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0597_allowed if {
    data.policies.security.enabled
}
policy_0597_allowed if {
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
