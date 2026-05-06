package access.authentication.resource.validate.utils.policy_0673

# Auto-generated policy 673
# Package: access.authentication.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0673",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0673_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0673_allowed if {
    input.user.active
    input.resource.public
}
policy_0673_allowed if {
    data.policies.access.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
