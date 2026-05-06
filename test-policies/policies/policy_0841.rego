package audit.authentication.action.verify.logic.policy_0841

# Auto-generated policy 841
# Package: audit.authentication.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0841",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0841_allowed if {
    input.user.active
    input.resource.public
}
policy_0841_allowed if {
    data.policies.audit.enabled
}
policy_0841_denied if {
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
