package access.enforcement.resource.allow.helpers.policy_0107

# Auto-generated policy 107
# Package: access.enforcement.resource.allow.helpers

# Metadata
metadata := {
    "policy_id": "0107",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0107_allowed if {
    input.user.role == "admin"
}
policy_0107_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0107_allowed if {
    data.policies.access.enabled
}
default policy_0107_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
