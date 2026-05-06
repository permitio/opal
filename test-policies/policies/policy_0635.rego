package access.enforcement.resource.deny.utils.policy_0635

# Auto-generated policy 635
# Package: access.enforcement.resource.deny.utils

# Metadata
metadata := {
    "policy_id": "0635",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0635_allowed if {
    input.user.role == "admin"
}
policy_0635_allowed if {
    data.policies.access.enabled
}
policy_0635_allowed if {
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
