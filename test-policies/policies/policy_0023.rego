package audit.authorization.user.check.policy_0023

# Auto-generated policy 23
# Package: audit.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0023",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0023_allowed = false
policy_0023_allowed if {
    input.user.active
    input.resource.public
}
policy_0023_allowed if {
    data.policies.audit.enabled
}
policy_0023_denied if {
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
