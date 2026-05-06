package security.authentication.context.deny.helpers.policy_0103

# Auto-generated policy 103
# Package: security.authentication.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0103",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0103_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0103_allowed if {
    input.user.role == "admin"
}
policy_0103_allowed if {
    data.policies.security.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
