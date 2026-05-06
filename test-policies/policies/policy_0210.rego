package access.authentication.resource.allow.logic.policy_0210

# Auto-generated policy 210
# Package: access.authentication.resource.allow.logic

# Metadata
metadata := {
    "policy_id": "0210",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0210_allowed = false
policy_0210_allowed if {
    data.policies.access.enabled
}
policy_0210_allowed if {
    input.user.role == "admin"
}
policy_0210_denied if {
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
