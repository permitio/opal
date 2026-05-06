package security.authentication.resource.check.policy_0531

# Auto-generated policy 531
# Package: security.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0531",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0531_allowed if {
    input.user.active
    input.resource.public
}
policy_0531_denied if {
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
