package access.validation.resource.check.helpers.policy_0719

# Auto-generated policy 719
# Package: access.validation.resource.check.helpers

# Metadata
metadata := {
    "policy_id": "0719",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0719_allowed = false
policy_0719_allowed if {
    data.policies.access.enabled
}
policy_0719_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0719_allowed if {
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
