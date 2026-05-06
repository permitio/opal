package audit.authorization.context.allow.policy_0589

# Auto-generated policy 589
# Package: audit.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0589",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0589_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0589_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
