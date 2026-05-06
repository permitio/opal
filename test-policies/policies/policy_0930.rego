package access.validation.context.verify.policy_0930

# Auto-generated policy 930
# Package: access.validation.context.verify

# Metadata
metadata := {
    "policy_id": "0930",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0930_allowed if {
    data.policies.access.enabled
}
default policy_0930_allowed = false
policy_0930_allowed if {
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
