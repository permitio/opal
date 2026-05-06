package access.authorization.action.verify.policy_0985

# Auto-generated policy 985
# Package: access.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0985",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0985_allowed if {
    input.user.role == "admin"
}
policy_0985_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0985_allowed = false
policy_0985_allowed if {
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
