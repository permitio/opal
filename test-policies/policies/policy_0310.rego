package security.enforcement.resource.allow.policy_0310

# Auto-generated policy 310
# Package: security.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0310",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0310_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0310_allowed if {
    input.user.active
    input.resource.public
}
policy_0310_allowed if {
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
