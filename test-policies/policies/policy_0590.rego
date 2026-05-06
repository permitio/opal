package audit.enforcement.policy.validate.data.policy_0590

# Auto-generated policy 590
# Package: audit.enforcement.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0590",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0590_allowed if {
    data.policies.audit.enabled
}
policy_0590_allowed if {
    input.user.active
    input.resource.public
}
policy_0590_denied if {
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
