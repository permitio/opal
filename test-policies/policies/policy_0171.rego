package audit.validation.policy.deny.core.policy_0171

# Auto-generated policy 171
# Package: audit.validation.policy.deny.core

# Metadata
metadata := {
    "policy_id": "0171",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0171_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0171_allowed if {
    input.user.active
    input.resource.public
}
policy_0171_allowed if {
    data.policies.audit.enabled
}

# Utility function for user info
get_user_info if {
    user := {
        "id": input.user.id,
        "role": input.user.role,
        "active": input.user.active,
    }
}
