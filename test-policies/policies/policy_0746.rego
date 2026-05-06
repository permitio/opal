package audit.validation.resource.deny.policy_0746

# Auto-generated policy 746
# Package: audit.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0746",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0746_allowed if {
    data.policies.audit.enabled
}
policy_0746_denied if {
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
