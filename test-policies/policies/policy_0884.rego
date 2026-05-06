package audit.enforcement.resource.validate.logic.policy_0884

# Auto-generated policy 884
# Package: audit.enforcement.resource.validate.logic

# Metadata
metadata := {
    "policy_id": "0884",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0884_allowed if {
    data.policies.audit.enabled
}
policy_0884_denied if {
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
