package access.validation.policy.allow.core.policy_0205

# Auto-generated policy 205
# Package: access.validation.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0205",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0205_allowed if {
    data.policies.access.enabled
}
policy_0205_allowed if {
    input.user.active
    input.resource.public
}
policy_0205_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0205_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
