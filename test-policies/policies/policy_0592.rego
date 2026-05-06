package access.enforcement.user.validate.logic.policy_0592

# Auto-generated policy 592
# Package: access.enforcement.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0592",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0592_allowed if {
    input.user.role == "admin"
}
policy_0592_allowed if {
    data.policies.access.enabled
}
policy_0592_denied if {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
