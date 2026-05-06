package security.authentication.resource.check.policy_0800

# Auto-generated policy 800
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0800",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0800_allowed = false
policy_0800_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
