package security.authorization.policy.allow.logic.policy_0496

# Auto-generated policy 496
# Package: security.authorization.policy.allow.logic

# Metadata
metadata := {
    "policy_id": "0496",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0496_allowed if {
    input.user.role == "admin"
}
policy_0496_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0496_allowed = false
policy_0496_allowed if {
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
