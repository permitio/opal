package security.authorization.resource.validate.core.policy_0775

# Auto-generated policy 775
# Package: security.authorization.resource.validate.core

# Metadata
metadata := {
    "policy_id": "0775",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0775_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0775_allowed if {
    data.policies.security.enabled
}
policy_0775_allowed if {
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
