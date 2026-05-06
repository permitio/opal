package audit.validation.policy.deny.policy_0530

# Auto-generated policy 530
# Package: audit.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0530",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0530_allowed if {
    data.policies.audit.enabled
}
policy_0530_allowed if {
    input.user.active
    input.resource.public
}
policy_0530_denied if {
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
