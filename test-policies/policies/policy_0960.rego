package security.enforcement.policy.check.policy_0960

# Auto-generated policy 960
# Package: security.enforcement.policy.check

# Metadata
metadata := {
    "policy_id": "0960",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0960_allowed if {
    data.policies.security.enabled
}
policy_0960_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0960_allowed if {
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
