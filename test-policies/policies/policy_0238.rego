package security.authentication.context.check.policy_0238

# Auto-generated policy 238
# Package: security.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0238",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0238_allowed if {
    input.user.role == "admin"
}
policy_0238_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0238_allowed if {
    data.policies.security.enabled
}
policy_0238_allowed if {
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
