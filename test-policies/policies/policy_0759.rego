package security.authorization.policy.deny.policy_0759

# Auto-generated policy 759
# Package: security.authorization.policy.deny

# Metadata
metadata := {
    "policy_id": "0759",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0759_allowed if {
    input.user.active
    input.resource.public
}
policy_0759_allowed if {
    data.policies.security.enabled
}
policy_0759_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0759_allowed = false

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
