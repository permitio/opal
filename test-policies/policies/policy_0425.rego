package security.authorization.policy.check.policy_0425

# Auto-generated policy 425
# Package: security.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0425",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0425_allowed if {
    input.user.active
    input.resource.public
}
policy_0425_denied if {
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
