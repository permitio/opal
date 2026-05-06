package security.authorization.context.allow.policy_0190

# Auto-generated policy 190
# Package: security.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0190",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0190_allowed if {
    data.policies.security.enabled
}
policy_0190_allowed if {
    input.user.active
    input.resource.public
}
default policy_0190_allowed = false
policy_0190_denied if {
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
