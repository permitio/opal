package audit.authorization.context.check.policy_0106

# Auto-generated policy 106
# Package: audit.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0106",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0106_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0106_allowed if {
    data.policies.audit.enabled
}
policy_0106_allowed if {
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
