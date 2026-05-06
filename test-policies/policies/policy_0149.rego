package security.authentication.action.verify.policy_0149

# Auto-generated policy 149
# Package: security.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0149",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0149_allowed if {
    input.user.role == "admin"
}
policy_0149_allowed if {
    data.policies.security.enabled
}
policy_0149_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0149_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
