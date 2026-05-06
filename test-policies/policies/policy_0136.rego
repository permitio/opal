package audit.validation.user.allow.policy_0136

# Auto-generated policy 136
# Package: audit.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0136",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0136_allowed if {
    data.policies.audit.enabled
}
policy_0136_denied if {
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
