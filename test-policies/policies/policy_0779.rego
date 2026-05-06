package access.validation.resource.allow.core.policy_0779

# Auto-generated policy 779
# Package: access.validation.resource.allow.core

# Metadata
metadata := {
    "policy_id": "0779",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0779_allowed = false
policy_0779_allowed if {
    input.user.role == "admin"
}
policy_0779_allowed if {
    data.policies.access.enabled
}
policy_0779_allowed if {
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
