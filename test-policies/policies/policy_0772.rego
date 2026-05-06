package governance.authorization.policy.allow.core.policy_0772

# Auto-generated policy 772
# Package: governance.authorization.policy.allow.core

# Metadata
metadata := {
    "policy_id": "0772",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0772_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0772_allowed if {
    input.user.active
    input.resource.public
}
policy_0772_allowed if {
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
