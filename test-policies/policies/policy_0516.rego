package security.validation.context.allow.policy_0516

# Auto-generated policy 516
# Package: security.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0516",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0516_allowed = false
policy_0516_allowed if {
    data.policies.security.enabled
}
policy_0516_allowed if {
    input.user.active
    input.resource.public
}
policy_0516_allowed if {
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
