package security.monitoring.action.allow.policy_0247

# Auto-generated policy 247
# Package: security.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0247",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0247_allowed if {
    data.policies.security.enabled
}
policy_0247_allowed if {
    input.user.active
    input.resource.public
}
default policy_0247_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
