package audit.validation.policy.deny.policy_0860

# Auto-generated policy 860
# Package: audit.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0860",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0860_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0860_allowed if {
    data.policies.audit.enabled
}
policy_0860_allowed if {
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
